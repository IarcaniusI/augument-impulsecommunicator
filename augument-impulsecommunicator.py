import re
import sys
import praw
import argparse
import json
import random
import signal
from datetime import datetime

PROCESS_NAME = "augument-impulsecommunicator"
NO_NOTIFY = False

# register enhancing for use: https://www.reddit.com/prefs/apps

def signal_term_handler(signal, frame):
    exit_time = datetime.now().isoformat().replace("T", " ")
    print(exit_time, '|', PROCESS_NAME, 'terminated')
    sys.exit(0)

def critical_print(*messages, action=None):
    if action is not None:
        action()

    err_time = datetime.now().isoformat().replace("T", " ")
    print(err_time, "|", *messages, file=sys.stderr)
    sys.exit()

def main():
    # handle unix signal before exiting
    signal.signal(signal.SIGTERM, signal_term_handler)
    signal.signal(signal.SIGINT, signal_term_handler)

    start_time = datetime.now().isoformat().replace("T", " ")
    print(start_time, '|', PROCESS_NAME, 'started')

    # parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--auth', default=["auth.conf"], nargs=1,
                        help="Path to file with auth settings.")
    parser.add_argument('-r', '--run', default=["run.conf"], nargs=1,
                        help="Path to file with run settings.")
    parser.add_argument('-n', '--no-notify', action='store_true', default=False,
                        help="Disable log notification messages (REPLIES).")
    command_arg = parser.parse_args()
    if command_arg.no_notify:
        NO_NOTIFY = True

    # set filenames for files with auth and run settings
    auth_filename = command_arg.auth[0]
    run_filename = command_arg.run[0]
    print("Auth file name: ", auth_filename)
    print("Run file name: ", run_filename)

    # load info from settings files
    auth_settings = load_auth_settings(auth_filename)
    run_settings = load_run_settings(run_filename)

    # reddit authentication
    try:
        my_user, subreddit = auth(auth_settings)
    except Exception as err:
        critical_print("Can't auth : ", err)

    # script main function executing
    try:
        process_comments_stream(my_user, subreddit, run_settings)
    except Exception as err:
        critical_print("Runtime error : ", err)

# reddit authentication, username and subreddit obtaining
# argument s - dict with auth settings
def auth(s: dict):
    reddit = praw.Reddit(user_agent=s.get("user_agent"),
                            client_id=s.get("client_id"), client_secret=s.get("client_secret"),
                            username=s.get("username"), password=s.get("password"))
    my_user = reddit.user.me()

    auth_time = datetime.now().isoformat().replace("T", " ")
    print(auth_time, "|", PROCESS_NAME, "authenticated, user name: '", my_user, "'")
    subreddit = reddit.subreddit(s.get("subreddit"))
    print("Subredit name: ", subreddit)
    return my_user, subreddit

# main sctipt function
def process_comments_stream(my_user, subreddit, run_settings: dict) -> None:
    # process every comment obtained from reddit online stream
    for comment in subreddit.stream.comments():
        comment_body = comment.body.lower()
        parent_type = type(comment.parent())

        # process every rule for comment
        for rule in run_settings:
            # check name of commentor and permission of reply
            if (comment.author.name == rule.get("bot_name")):
                correct_reply_on = check_reply_on(parent_type, rule.get("reply_on"))
                if correct_reply_on:
                    answer = random.choice(rule.get("answers"))

                    if not NO_NOTIFY:
                        reply_time = datetime.now().isoformat().replace("T", " ")
                        print(reply_time, "| REPLY:", comment_body, ":", answer)

                    if reply_to == "bot":
                        comment.reply(answer)
                    elif reply_to == "invoker":
                        comment.parent().reply(answer)

# return true if nessesary type of reply
def check_reply_on(parent_type, reply_on, reply_to):
    correct_reply_on = False
    if (parent_type is praw.models.reddit.comment.Comment) and (
        (reply_on == "both" or reply_on == "comment")):
        correct_reply_on = True

    if (parent_type is praw.models.reddit.submission.Submission) and (
        (reply_on == "both" or reply_on == "post")):

        # there are no invokers in this case
        if reply_to != "invoker":
            correct_reply_on = True

    return correct_reply_on

# parse JSON file with auth settings and check it
def load_auth_settings(filename: str) -> dict:
    # read settings from JSON file
    try:
        read_file = open(filename, "r")
    except Exception as err:
        critical_print("Can't open file '", filename, "' : ", err, action=read_file.close)
    else:
        try:
            auth_settings = json.load(read_file)
        except Exception as err:
            critical_print("Impossible to parse file '", filename, "' : ", err, action=read_file.close)
    finally:
        read_file.close()

    # check type of auth settings
    auth_params = ["user_agent", "client_id", "client_secret", "username", "password" ,"subreddit"]
    if type(auth_settings) is not dict:
        critical_print("Incorrect root element in file '", filename, "'")
    else:
        for auth_param in auth_params:
            if type(auth_settings.get(auth_param)) is not str:
                critical_print("Incorrect argument '", auth_param, "' in file '", filename, "'")

    return auth_settings

# parse JSON file with  run settings
def load_run_settings(filename: str) -> list:
    # read settings from JSON file
    try:
        read_file = open(filename, "r")
    except Exception as err:
        critical_print("Can't open file '", filename, "' : ", err, action=read_file.close)
    else:
        try:
            run_settings = json.load(read_file)
        except Exception as err:
            critical_print("Impossible to parse file '", filename, "' : ", err, action=read_file.close)
    finally:
        read_file.close()

    # check type of run settings
    if type(run_settings) is not list:
        critical_print("Incorrect root element in file '", filename, "'")
    else:
        for i, rule in enumerate(run_settings):
            if type(rule) is not dict:
                critical_print("Incorrect rule '", str(i),"' in file '", filename, "'")
            else:
                #check str rule params "bot_name" and "reply_on"
                rule_params_str = ["bot_name", "reply_on", "reply_to"]
                for rule_param in rule_params_str:
                    if type(rule.get(rule_param)) is not str:
                        critical_print("Incorrect argument '", rule_param, "' in rule '",
                            str(i), "' in file '", filename, "'")

                # "reply_on" can be a "post", "comment" or "both"
                value = rule.get("reply_on")
                if (value != "post") and (value != "comment") and (value != "both"):
                    critical_print("Incorrect value for 'reply_on' in rule '", str(i),
                        "' in file '", filename, "'. Possible values: post, comment, both")

                # "reply_to" can be a "bot" or "invoker"
                value = rule.get("reply_to")
                if (value != "invoker") and (value != "bot"):
                    critical_print("Incorrect value for 'reply_to' in rule '", str(i),
                        "' in file '", filename, "'. Possible values: bot, invoker")

                #check rule param "answers"
                if type(rule.get("answers")) is not list:
                    critical_print("Incorrect argument 'answers' in rule '",
                        str(i), "' in file '", filename, "'")
                else:
                    for answer in rule.get("answers"):
                        if type(answer) is not str:
                            critical_print("Incorrect string value in parameter 'answers' in rule '",
                                str(i), "' in file '", filename, "'")

    return run_settings

if __name__ == "__main__":
    main()
