"""Conversion script from folder to hr/lr pair.

@author zeptofine
"""
import os
import sys
from argparse import ArgumentParser
from datetime import datetime
from functools import lru_cache
from glob import glob
from pathlib import Path
from subprocess import SubprocessError

from ConfigArgParser import ConfigParser
from util.pip_helpers import PipInstaller
from util.print_funcs import p_bar_stat
from util.process_funcs import is_subprocess

CPU_COUNT: int = os.cpu_count()  # type: ignore


if sys.platform == "win32":
    print("This application was not made for windows. Try Using WSL2")
    from time import sleep
    sleep(3)

packages = {'rich':            "rich",
            'opencv-python':   "cv2",
            'python-dateutil': "dateutil",
            'imagesize':       "imagesize",
            'rich-argparse':   "rich_argparse",
            'tqdm':            "tqdm",
            'shtab':           "shtab"}

with PipInstaller() as p:
    try:
        # loop import packages
        for i, package in enumerate(packages):
            print(f"{p_bar_stat(i, len(packages))}", end="\r")
            if not p.available(packages[package]):
                raise ImportError

    except (ImportError, ModuleNotFoundError):
        # Try to install packages
        try:
            for i, package in enumerate(packages):
                if not p.available(packages[package]):
                    print(f"{p_bar_stat(i, len(packages))}")
                    columns = os.get_terminal_size().columns
                    print(
                        f"{'-'*columns}\n" + str(f"{package} not detected. Attempting to install...").center(columns))
                    p.install(package)
                    if not p.available(packages[package]):
                        raise ModuleNotFoundError(
                            f"Failed to install '{package}'.")
            # restart process once installing required packages is complete
            if not is_subprocess():
                os.execv(sys.executable, ['python', *sys.argv])
            else:  # process failed even after installation, so something may be wrong with perms idk
                raise SubprocessError("Failed to install packages.")
        except (SubprocessError, ModuleNotFoundError) as err2:
            print(f"{type(err2).__name__}: {err2}")
            sys.exit(127)  # command not found

    else:
        print("\033[2K", end="")
        from rich.traceback import install
        install()

        import cv2
        import dateutil.parser as timeparser
        import imagesize
        from rich_argparse import ArgumentDefaultsRichHelpFormatter
        from tqdm import tqdm

        from util.iterable_starmap import poolmap
        from util.print_funcs import RichStepper
        s = RichStepper(loglevel=1, step=-1)


def main_parser() -> ArgumentParser:
    parser = ArgumentParser(
        formatter_class=ArgumentDefaultsRichHelpFormatter,
        description="""Hi! this script converts thousands of files to
    another format in a High-res/Low-res pairs for data science.
    @ is available to follow a file.""",
        fromfile_prefix_chars="@")

    import shtab
    shtab.add_argument_to(parser)

    p_reqs = parser.add_argument_group("Runtime")
    p_reqs.add_argument("-i", "--input",
                        help="Input folder.")
    p_reqs.add_argument("-x", "--scale", type=int, default=4,
                        help="scale to downscale LR images")
    p_reqs.add_argument("-e", "--extension", metavar="EXT", default=None,
                        help="export extension.")
    p_mods = parser.add_argument_group("Modifiers")
    p_mods.add_argument("-r", "--recursive", action="store_true", default=False,
                        help="preserves the tree hierarchy.")
    p_mods.add_argument("-t", "--threads", type=int, default=int((CPU_COUNT / 4) * 3),
                        help="number of total threads.")  # used for multiprocessing
    p_mods.add_argument("--image_limit", type=int, default=None, metavar="MAX",
                        help="only gathers a given number of images. None disables it entirely.")  # max numbers to be given to the filters
    p_mods.add_argument("--limit_mode", choices=["before", "after"], default="before",
                        help="Changes the order of the limiter. By default, it happens before filtering out bad images.")
    # ^^ this choice is for if you want to convert n images, or only search n images.
    p_mods.add_argument("--anonymous", action="store_true",
                        help="hides path names in progress. Doesn't affect the result.")
    p_mods.add_argument("--simulate", action="store_true",
                        help="skips the conversion step. Used for debugging.")
    p_mods.add_argument("--purge", action="store_true",
                        help="Clears the output folder before running.")
    p_mods.add_argument("--purge_only", action="store_true",
                        help="--purge, but finishes afterwards.")
    p_mods.add_argument("--sort", choices=["name", "ext", "len", "res", "time", "size"], default="res",
                        help="sorting method.")
    p_mods.add_argument("--reverse", action="store_true",
                        help="reverses the sorting direction. it turns smallest-> largest to largest -> smallest")
    p_mods.add_argument("--overwrite", action="store_true",
                        help="Skips checking for existing files, and by proxy, overwrites existing files.")
    # certain criteria that images must meet in order to be included in the processing.
    p_filters = parser.add_argument_group("Filters")
    p_filters.add_argument("--whitelist", type=str, metavar="INCLUDE",
                           help="only allows paths with the given string.")
    p_filters.add_argument("--blacklist", type=str, metavar="EXCLUDE",
                           help="excludes paths with the given string.")
    # ^^ used for restricting the names allowed in the paths.

    p_filters.add_argument("--minsize", type=int, metavar="MIN", default=128,
                           help="smallest available image")
    p_filters.add_argument("--maxsize", type=int, metavar="MAX",
                           help="largest allowed image.")
    p_filters.add_argument("--crop_mod", action="store_true",
                           help="changes mod mode so that it crops the image to an image that actually is divisible by scale, typically by a few px")
    # ^^ used for filtering out too small or too big images.
    p_filters.add_argument("--after", type=str,
                           help="Only uses files modified after a given date."
                           "ex. '2020', or '2009 Sept 16th'")
    p_filters.add_argument("--before", type=str,
                           help="Only uses before a given date. ex. 'Wed Jun 9 04:26:40', or 'Jun 9'")
    # ^^ Used for filtering out too old or too new images.
    return parser


# def next_step(order, *args) -> None:
#     output = {-1: "[yellow]INFO[/yellow]",
#               -2: "[orange]WARNING[/orange]",
#               -3: "[grey]DEBUG[/grey]",
#               -9: "[red]ERROR[/red]",
#               }.get(order, f"[blue]{order}[/blue]")
#     output = [f" {output}: {text}" for text in args]
#     rprint("\n".join(output), end="\n\033[K")

# class File:
#     def __init__(self, p: Path):
#         self.path = Path(p)
#         self.resolution = None
#         self.st = None

#     def stat(self):
#         self.st = self.st or self.p.stat()
#         return self.st

#     def res(self):
#         self.resolution = self.resolution or imagesize.get(self.p)
#         return self.resolution

#     def __repr__(self):
#         return self.path

@lru_cache
def get_resolution(path: Path):
    """
    Args    path: The path to the image file.
    Returns tuple[width, height]."""
    return imagesize.get(path) or cv2.imread(path).shape[:2]


def get_file_list(*folders: Path) -> list[Path]:
    """
    Args    folders: One or more folder paths.
    Returns list[Path]: paths in the specified folders."""
    globlist = [glob(str(p), recursive=True)
                for p in folders]
    return [Path(y) for x in globlist for y in x]


def get_existing(*folders) -> set[Path]:
    """
    Returns the files that already exist in the specified folders.
    Args    *: folders to be searched & compared.
    Returns tuple[set[Path], set[Path]]: HR and LR file paths in sets.
    """
    sets = ({f.relative_to(folder).with_suffix('')
            for f in get_file_list((folder / "**" / "*"))} for folder in folders)
    outset = set.intersection(*sets)
    return outset


def to_recursive(path: Path, recursive: bool) -> Path:
    """
    Convert the file path to a recursive path if recursive is False
    Ex: i/path/to/image.png => i/path_to_image.png"""
    return path if recursive else Path(str(path).replace(os.sep, "_"))


def check_for_images(image_list) -> None:
    if not list(image_list):
        s.print(-1, "No images left to process")
        sys.exit(0)


def whitelist(imglist, whitelist):
    return {j for i in whitelist for j in imglist if i in str(j)}


def blacklist(imglist, blacklist):
    imglist_with_blacklist = whitelist(imglist, blacklist)
    return set(imglist).difference(imglist_with_blacklist)


def hrlr_pair(path: Path, hr_folder: Path, lr_folder: Path,
              recursive: bool = False, ext=None) -> tuple[Path, Path]:
    """
    gets the HR and LR file paths for a given file or directory path.
    Args    recursive (bool): Whether to search for the file in subdirectories.
            ext (str): The file extension to append to the file name.
    Returns tuple[Path, Path]: HR and LR file paths.
    """
    hr_path = hr_folder / to_recursive(path, recursive)
    lr_path = lr_folder / to_recursive(path, recursive)
    # Create the HR and LR folders if they do not exist
    hr_path.parent.mkdir(parents=True, exist_ok=True)
    lr_path.parent.mkdir(parents=True, exist_ok=True)
    # If an extension is provided, append it to the HR and LR file paths
    if ext:
        hr_path = hr_path.with_suffix(f".{ext}")
        lr_path = lr_path.with_suffix(f".{ext}")
    return hr_path, lr_path


def within_time(inpath, before_time, after_time) -> tuple[bool, float]:
    """
    Checks if an image is within specified time limits.
    Args    inpath: the path to the image file.
            before_time: the image must be before this time.
            after_time: the image must be after this time.
    Returns tuple[success, filestat].
    """
    mstat = inpath.stat()
    filetime = datetime.fromtimestamp(mstat.st_mtime)
    if before_time or after_time:
        return (not (before_time and (before_time < filetime)) or (after_time and (after_time > filetime)), mstat)
    return (True, mstat)


def within_res(inpath, minsize, maxsize, scale, crop_mod) -> tuple[bool, tuple]:
    """
    Checks if an image is within specified resolution limits.
    Args    inpath: The path to the image file.
            minsize: The minimum allowed resolution for the image.
            maxsize: The maximum allowed resolution for the image.
            scale: The scale factor to use when checking the resolution.
            crop_mod: A boolean value indicating whether to crop the image to the nearest multiple of the scale factor.
    Returns tuple[success, resolution].
    """
    res = get_resolution(inpath)  # => (width, height)
    if crop_mod:
        # crop the image to the nearest multiple of the scale factor
        res = (res[0] // scale) * scale, (res[1] // scale) * scale
    return (
        (res[0] % scale == 0 and res[1] % scale == 0) and not (
            ((minsize and (res[0] < minsize or res[1] < minsize)) or
             (maxsize and (res[0] > maxsize or res[1] > maxsize)))),
        res
    )


def within_time_and_res(img_path, before, after, minsize, maxsize, scale, crop_mod) -> tuple[bool, tuple, tuple]:
    # filter images that are too young or too old
    t = within_time(img_path, before, after)

    # filter images that are too small or too big, or not divisible by scale
    r = within_res(img_path, minsize, maxsize, scale, crop_mod)
    return (t[0] and r[0]), t[1], r[1]


def filter_images(args, imglist, cparser: ConfigParser) -> tuple[tuple, dict, dict]:

    pargs = [(args.input / i,
              args.before, args.after,
              args.minsize, args.maxsize,
              args.scale, args.crop_mod) for i in imglist]
    mapped_list = {(i[0], *i[1][1:]) for i in filter(
        lambda x: x[1][0],
        zip(imglist,
            poolmap(args.threads, within_time_and_res, pargs, postfix=False, desc="Filtering")))}

    check_for_images(mapped_list)
    imglist, mstat, mres = zip(*mapped_list)
    mstat = {imglist[i]: v for i, v in enumerate(mstat)}
    mres = {imglist[i]: v for i, v in enumerate(mres)}

    # Make a tooltip to the user if not cropped_before
    if not (cparser.file.get("cropped_before", False) or args.crop_mod):
        s.print(-1, "Try the cropping mode! It crops the image instead of outright ignoring it.")
        cparser.file.update({"cropped_before": True}).save()

    return imglist, mstat, mres


def fileparse(inpath: Path, source: Path, mtime, scale: int,
              hr_folder: Path, lr_folder: Path,
              recursive: bool, ext=None) -> Path:
    """
    Converts an image file to HR and LR versions and saves them to the specified folders.
    Returns tuple[Path, tuple[...]]: solely for printing.
    """
    # Generate the HR & LR file paths
    hr_path, lr_path = hrlr_pair(inpath, hr_folder, lr_folder, recursive, ext)

    # Read the image file
    image = cv2.imread(source, cv2.IMREAD_UNCHANGED)  # type: ignore
    image = image[0:(image.shape[0] // scale) * scale,
                  0:(image.shape[1] // scale) * scale]

    # Save the HR / LR version of the image
    cv2.imwrite(str(hr_path), image)  # type: ignore
    cv2.imwrite(str(lr_path), cv2.resize(  # type: ignore
        image, (0, 0), fx=1 / scale, fy=1 / scale))

    # Set the modification time of the HR and LR image files to the original image's modification time
    os.utime(str(hr_path), (mtime, mtime))
    os.utime(str(lr_path), (mtime, mtime))

    # Return the input path of the image file
    return inpath


def main():
    cparser = ConfigParser(main_parser(), "config.json", exit_on_change=True)
    args = cparser.parse_args()

# make sure args are valid
    if not (args.input):
        sys.exit("Please specify an input directory.")
    if args.extension:
        if args.extension.startswith("."):
            args.extension = args.extension[1:]
        if args.extension.lower() in ["self", "none", "same", ""]:
            args.extension = None
    if args.after or args.before:
        try:
            if args.after:
                args.after = timeparser.parse(str(args.after))
            if args.before:
                args.before = timeparser.parse(str(args.before))
            if args.after and args.before and args.after > args.before:
                raise timeparser.ParserError(
                    f"{args.before} (--before) is older than {args.after} (--after)!")
        except timeparser.ParserError as err:
            s.set(-9).print(str(err))
            return 1

    s.next("Settings: ")
    s.print(f"  input: {args.input}",
            f"  scale: {args.scale}",
            f"  threads: {args.threads}",
            f"  extension: {args.extension}",
            f"  recursive: {args.recursive}",
            f"  anonymous: {args.anonymous}",
            f"  crop_mod: {args.crop_mod}",
            f"  sort: {args.sort}, reverse: {args.reverse}")

    s.next("Gathering images...")
    args.input = Path(args.input).resolve()
    image_list = get_file_list(args.input / "**" / "*.png",
                               args.input / "**" / "*.jpg",
                               args.input / "**" / "*.webp")
    if args.image_limit and args.limit_mode == "before":  # limit image number
        image_list = image_list[:args.image_limit]
    s.print(f"Gathered {len(image_list)} images")

# filter out blacklisted/whitelisted items
    if args.whitelist:
        args.whitelist = args.whitelist.split(" ")
        image_list = whitelist(image_list, args.whitelist)
        s.print(f"whitelist {args.whitelist}: {len(image_list)}")
    if args.blacklist:
        args.blacklist = args.blacklist.split(" ")
        image_list = blacklist(image_list, args.blacklist)
        s.print(f"blacklist {args.blacklist}: {len(image_list)}")

# discard symbolic duplicates
    original_total = len(image_list)
    # vv This naturally removes the possibility of multiple files pointing to the same image
    image_list = {i.resolve(): i.relative_to(args.input)
                  for i in tqdm(image_list, desc="Resolving")}.values()
    if len(image_list) != original_total:
        s.print(f"Discarded {original_total - len(image_list)} symbolic links")

# get hr / lr folders
    hr_folder = args.input.parent / f"{str(args.scale)}xHR"
    lr_folder = args.input.parent / f"{str(args.scale)}xLR"
    if args.extension:
        hr_folder = Path(f"{str(hr_folder)}-{args.extension}")
        lr_folder = Path(f"{str(lr_folder)}-{args.extension}")
    hr_folder.parent.mkdir(parents=True, exist_ok=True)
    lr_folder.parent.mkdir(parents=True, exist_ok=True)

# Purge existing images
    if args.purge or args.purge_only:
        s.next("Purging...")
        for path in image_list:
            hr_path, lr_path = hrlr_pair(path, hr_folder, lr_folder,
                                         args.recursive, args.extension)
            hr_path.unlink(missing_ok=True)
            lr_path.unlink(missing_ok=True)

        s.print("Purged.")
        if args.purge_only:
            return 0

# get files that were already converted
    original_total = len(image_list)
    if not args.overwrite:
        s.next("Removing existing")
        exist_list = get_existing(hr_folder, lr_folder)
        image_list = [i for i in tqdm(image_list, desc="Removing existing")
                      if to_recursive(i, args.recursive).with_suffix("") not in exist_list]
    s.print(
        f"Discarded {original_total-len(image_list)} images which already exist\n")

    check_for_images(image_list)

# remove files based on resolution and time
    s.next("Filtering images...")
    original_total = len(image_list)
    if args.before or args.after:
        s.print(f"Filtering by time ({args.before}<=x<={args.after})")
    if args.minsize or args.maxsize:
        s.print(f"Filtering by size ({args.minsize}<=x<={args.maxsize})")

    image_list, mstat, mres = filter_images(args, image_list, cparser)
    s.print(f"Discarded {original_total - len(image_list)} images\n")

    if args.simulate:
        s.next("Simulated")
        return 0

# Sort files based on different attributes
    s.next("Sorting...\n")
    sorting_methods = {"name": lambda x: x,
                       "ext": lambda x: x.suffix,
                       "len": lambda x: len(str(x)),
                       "res": lambda x: mres[x][0] * mres[x][1],
                       "time": lambda x: mstat[x].st_mtime,
                       "size": lambda x: mstat[x].st_size}
    image_list = sorted(image_list,
                        key=sorting_methods[args.sort], reverse=args.reverse)

    if args.image_limit and args.limit_mode == "after":  # limit image number
        image_list = set(image_list[:args.image_limit])

# create hr/lr pairs from list of valid images
    s.next(f"{len(image_list)} images in queue")
    try:
        pargs = [(v, str(args.input / v), mstat[v].st_mtime, args.scale,
                  hr_folder, lr_folder,
                  args.recursive, args.extension)
                 for v in image_list]
        image_list = poolmap(args.threads, fileparse, pargs,
                             chunksize=2,
                             postfix=not args.anonymous,
                             use_tqdm=True)
    except KeyboardInterrupt:
        s.print(-1, "KeyboardInterrupt")
    s.next("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
