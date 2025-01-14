import json
import os
from argparse import ArgumentParser

from cfg_param_wrapper import ConfigArgParser

parser = ArgumentParser()
parser.add_argument("-s", "--sort", action="store_true", help="Sorts the list of entries.")
parser.add_argument("--batch_path", default="Batches/", help="input for the folder name.")
parser.add_argument("-w", "--web", default="e621.net", help="input the website.")
parser.add_argument("--max", type=int, default=1000, help="max images to give per item.")
parser.add_argument("--output-fmt", default="%search_1%/%date:format=yyyy-MM-dd-hh-mm-ss%_%md5%_%rating%.%ext%")
parser.add_argument(
    "--post-filter",
    action="store_true",
    help="puts blacklisted terms in the postFiltering section. will pass onto tags otherwise.",
)
cparser = ConfigArgParser(parser, "config.json")
args = cparser.parse_args()

if not os.path.exists("prefixes.txt"):
    raise FileNotFoundError("You don't have a prefixes.txt file! (a prompt per line)")
with open("prefixes.txt", "r", encoding="utf-8") as prfile:
    prefixes = prfile.readlines()

outputJson = {"batchs": [], "uniques": [], "version": 3}

prefixes = map(lambda i: i.strip().split(" "), prefixes)
blacklist = ["watersports", "urine", "gore", "vore", "loli"]
blacklist = [f"-{i}" for i in blacklist]

assert prefixes, "Your prefixes.txt is empty. Fill it up with prompts"

for prompt in prefixes:
    tmpdict = {
        "filename": args.output_fmt,
        "galleriesCountAsOne": True,
        "getBlacklisted": False,
        "page": 1,
        "perpage": 60,
        "path": args.batch_path,
        "site": args.web,
        "total": args.max,
    }
    tmpdict.update({"query": {"tags": prompt}})
    # if not --postFilter, then add blacklist to the prompt with --
    if not args.post_filter:
        tmpdict["query"]["tags"] += blacklist
    else:
        tmpdict["postFiltering"] = blacklist

    outputJson["batchs"].append(tmpdict)

with open("imgbrd_grabbergen.igl", "w", encoding="utf-8") as outfile:
    outfile.write(json.dumps(outputJson, indent=4))
