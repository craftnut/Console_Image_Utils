
import os
from datetime import datetime
from pathlib import Path

import polars as pl
from cfg_argparser import CfgDict
from polars import DataFrame
from tqdm import tqdm

from util.print_funcs import byte_format

from dataset_filters.data_filters import DataFilter


def current_time() -> datetime:
    return datetime.now().replace(microsecond=0)
    # return datetime.fromtimestamp(time.time())


class DatasetBuilder:
    def __init__(self, rich_stepper_object, origin: str, processes=1):
        super().__init__()
        self.filters: list[DataFilter] = []
        self.power = processes
        self.stepper = rich_stepper_object
        self.origin = origin  # necessary for certain filters to work

        self.config = CfgDict("database_config.json", {
            "trim": True,
            'trim_age_limit': 60 * 60 * 24 * 7,
            "trim_check_exists": True,
            "save_interval": 500,
            "chunksize": 100,
            "filepath": "filedb.feather"
        }, autofill=True)
        self.filepath = self.config['filepath']
        self.time_threshold = self.config['trim_age_limit']

        self.basic_schema = {
            'path': str,
            'checkedtime': pl.Datetime
        }

        if os.path.exists(self.filepath):
            print("Reading database...")
            self.df = pl.read_ipc(self.config['filepath'], use_pyarrow=True)
            print("Finished.")
        else:
            self.df = DataFrame(schema=self.basic_schema)

    def absolute_dict(self, lst: set[Path]):
        return {(str((self.origin / pth).resolve())): pth for pth in lst}

    def populate_df(self, lst: set[Path]):
        from_full_to_relative = self.absolute_dict(lst)
        abs_paths = from_full_to_relative.keys()

        # build a new schema
        new_schema = dict(self.df.schema).copy()
        build_exprs = dict()
        for filter_ in self.filters:
            filter_.filedict = from_full_to_relative
            expr = filter_.build_schema
            if expr is not None:
                build_exprs.update(expr)
            schemas = filter_.column_schema
            new_schema.update({
                schema: value
                for schema, value in schemas.items()
                if schema not in self.df.schema
            })

        # add new paths to the dataframe with missing data
        existing_paths = set(self.df.select(pl.col('path')).to_series())
        new_paths = [path for path in abs_paths if path not in existing_paths]
        if new_paths:
            self.df = pl.concat(
                [
                    self.df,
                    DataFrame({
                        'path': new_paths,
                        'checkedtime': [current_time()] * len(new_paths)
                    })
                ],
                how="diagonal"
            )

        # get paths with missing data
        self.df = DatasetBuilder._make_schema_compliant(self.df, new_schema)
        unfinished = self.df.filter(pl.any(pl.col(col).is_null() for col in self.df.columns))
        try:
            if len(unfinished):
                with tqdm(desc="Gathering file info...", total=len(unfinished)) as t:
                    chunksize = self.config['chunksize']
                    save_timer = 0
                    collected_data = DataFrame(schema=new_schema)
                    for df_group in (
                        unfinished
                        .with_row_count('idx')
                        .with_columns(pl.col('idx') // chunksize)
                        .partition_by('idx')
                    ):
                        df_group.drop_in_place('idx')
                        new_data = df_group.with_columns(**{
                            col: pl.when(pl.col(col).is_null()).then(expr).otherwise(pl.col(col))
                            for col, expr in build_exprs.items()
                        })
                        collected_data.vstack(new_data, in_place=True)
                        t.update(len(df_group))
                        save_timer += chunksize
                        if save_timer > self.config['save_interval']:
                            self.df = self.df.update(collected_data, on='path')
                            self.save_df()
                            t.set_postfix_str(f"Autosaved at {current_time()}")
                            collected_data = collected_data.clear()
                            save_timer = 0

                self.df = self.df.update(collected_data, on='path').rechunk()
                self.save_df()
                self.stepper.print(f"new DB size: [bold yellow]{byte_format(self.get_db_disk_size())}[/bold yellow]")
        except KeyboardInterrupt as exc:
            print("KeyboardInterrupt detected! attempting to save dataframe...")
            self.save_df()
            print("Saved.")
            raise exc

        return

    def save_df(self):
        self.df.write_ipc(self.filepath)

    def get_db_disk_size(self):
        """gets the database size on disk."""
        return os.stat(self.config['filepath']).st_size

    @staticmethod
    def _make_schema_compliant(data_frame: DataFrame, schema) -> DataFrame:
        """adds columns from the schema to the dataframe. (not in-place)"""
        return pl.concat(
            [
                data_frame,
                DataFrame(schema=schema)
            ], how="diagonal"
        )

    def add_filters(self, *filters: DataFilter) -> None:
        '''Adds filters to the filter list.'''
        for filter_ in filters:
            filter_.set_origin(self.origin)
            self.filters.append(filter_)

    def filter(self, lst, sort_col="path"):
        assert sort_col in self.df.columns, "Sorting column is not in the database"
        from_full_to_relative = self.absolute_dict(lst)
        paths = from_full_to_relative.keys()
        with tqdm(self.filters, "Running full filters...") as t:
            vdf = self.df.filter(pl.col('path').is_in(paths)).rechunk()
            count = 0
            for dfilter in self.filters:
                vdf = vdf.filter(
                    dfilter.fast_comp()
                    if dfilter.is_fast else
                    pl.col('path').is_in(
                        dfilter.compare(
                            set(vdf.select(pl.col('path')).to_series()),
                            self.df.select(
                                pl.col('path'),
                                *[pl.col(col) for col in dfilter.column_schema]
                            )
                        )
                    )
                )
                t.update(count + 1)
                count = 0
            t.update(count)
        return [from_full_to_relative[p] for p in vdf.sort(sort_col).select(pl.col('path')).to_series()]

    def _apply(self, filter_filelist):
        filter_, filelist = filter_filelist
        return filter_.apply(filelist)

    def __enter__(self, *args, **kwargs):
        self.__init__(*args, **kwargs)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        pass
