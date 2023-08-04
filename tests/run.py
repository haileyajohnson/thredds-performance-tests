#!/usr/bin/env python3

import argparse
import glob
import json
import jsonschema
import logging
import os
import pandas as pd
import requests
import subprocess
import tempfile
import time

CONFIG_SCHEMA = {
    "type": "object",
    "required": ["name", "id"],
    "properties": {
        "name": {
            "type": "string",
        },
        "id": {
            "type": "string",
            "pattern": "^[a-z_]+([a-z0-9_]+)*$"
        },
        "description": {
            "type": "string",
        },
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "url"],
                "properties": {
                    "name": {
                        "type": "string",
                    },
                    "id": {
                        "type": "string",
                        "pattern": "^[a-z_]+([a-z0-9_]+)*$"
                    },
                    "description": {
                        "type": "string",
                    },
                    "url": {
                        "type": "string",
                    }
                }
            }
        }
    }
}

BASE_URL = "http://localhost:8080/thredds/"
CONFIG_DIR = "./configs/"
RESULTS_DIR = "./results/"
TIME = time.strftime("%Y%m%d-%H%M")
REQUESTS = 1000
TIMELIMIT = 10


def check_ids_are_unique(configs):
    ids = [test["id"] for k, v in configs.items() for test in v["tests"]]
    unique = len(set(ids)) == len(ids)
    if not unique:
        raise ValueError("Expected test ids to be unique, but found:", ids)


def parse_and_validate_configs():
    output = {}

    for config_file in glob.glob(CONFIG_DIR + "*"):
        with open(config_file, "r") as file_handle:
            json_contents = json.load(file_handle)
            jsonschema.validate(json_contents, schema=CONFIG_SCHEMA)
            output[config_file] = json_contents

    check_ids_are_unique(output)
    return output


def run_tests(test_configs, args):
    df_list = []

    for filename, config in test_configs.items():
        tests = config["tests"]
        for test in tests:
            url = test["url"]
            test_df = run_test(url, test, args)
            df_list.append(test_df)

    return pd.concat(df_list)


def run_test(url, test, args):
    with tempfile.NamedTemporaryFile() as out_file:
        command = [
            "ab",
            "-t",
            str(args.timelimit),
            "-n",
            str(args.requests),
            "-e",
            out_file.name,
            BASE_URL + url
        ]
        out = subprocess.run(
            command,
            capture_output=True,
            text=True)

        logging.info(out.stdout)
        logging.info(out.stderr)
        return make_df(out_file, test)


def make_df(file, test):
    df = pd.read_csv(file)

    df.insert(0, "datetime", TIME)
    df.insert(0, "description", test["description"])
    df.insert(0, "name", test["name"])
    df.insert(0, "id", test["id"])
    return df


def write_to_csv(df):
    df.to_csv(RESULTS_DIR + "results.csv", index=False)


def parse_cli_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-n",
        "--requests",
        nargs="?",
        default=REQUESTS,
        type=int,
        help="Number of requests to execute for each test."
    )
    parser.add_argument(
        "-t",
        "--timelimit",
        nargs="?",
        default=TIMELIMIT,
        type=int,
        help="Maximum seconds to spend per tests."
    )
    return parser.parse_args()


def check_connection():
    try:
        requests.get(BASE_URL)
    except Exception:
        raise ConnectionError("Cannot connect to TDS at: " + BASE_URL)


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    logging.basicConfig(
        filename=RESULTS_DIR + "run.log",
        level=logging.INFO,
        filemode="w")

    check_connection()

    args = parse_cli_args()
    test_configs = parse_and_validate_configs()
    df = run_tests(test_configs, args)
    write_to_csv(df)


if __name__ == "__main__":
    main()
