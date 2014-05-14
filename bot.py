# PictureGameBot by /u/Mustermind
# Requested by /u/malz_ for /r/PictureGame
#
# Pretty much my magnum opus when it comes to my bot-making skills.
#
# Requirements:
# - A subreddit where only the player account can post.
# - A bot account that moderates posts (must be a moderator)
# - A player account that is passed from person to person.
#
# Assumptions:
# - The subreddit is quite active, because the player account is expected to be
#   transferred quite quickly.
# - The bot is run constantly, without too many unexpected halts (there are some
#   failsafes, but they are not meant to be used frequently).
# - All players post in the format "[Round XXXX] Text text text...". If the post
#   deviates from the format even a little, the post wouldn't be counted as a
#   round. There is no enforcing of format yet.

import os
import re
import sys
import praw
import time
import base64
import pyimgur
import requests
from html import unescape
from textwrap import dedent
from multiprocessing import Process
from random import choice as sample
from urllib.request import urlretrieve
from xml.etree import ElementTree as ET

import warnings
warnings.filterwarnings("ignore", category=ResourceWarning)

class PictureGameBot:
  version = "0.4"
  user_agent = "/r/PictureGame Bot"
  
  def __init__(bot,gamebot=(None, None), player=(None, None),
               imgurid=None, subreddit="PictureGame"):
    # Public: Logs into the bot and the player account. Sets up imgur access.
    #
    #   gamebot - A tuple of username and password for the bot account.
    #    player - A tuple of username and password for the picturegame account.
    #             This is used to reset the password.
    #   imgurid - The Client ID used to log into Imgur.
    # subreddit - The subreddit to listen on.
    #
    # Returns an instance of PictureGameBot.
    bot.gamebot   = (os.environ.get("REDDIT_USERNAME", gamebot[0]),
                     os.environ.get("REDDIT_PASSWORD", gamebot[1]))
    bot.r_gamebot = praw.Reddit("%{:s}, v%{:s}".format(bot.user_agent,
                                                       bot.version))
    bot.r_gamebot.login(bot.gamebot[0], bot.gamebot[1])
    
    bot.player    = (os.environ.get("PLAYER_USERNAME", player[0]),
                     os.environ.get("PLAYER_PASSWORD", player[1]))
    bot.r_player  = praw.Reddit("/r/PictureGame Account")
    bot.r_player.login(bot.player[0], bot.player[1])
    
    bot.subreddit = bot.r_gamebot.get_subreddit(subreddit)
    bot.imgur     = pyimgur.Imgur(os.environ.get("IMGUR_ID", imgurid))
    
  def latest_round(bot):
    # Internal: Gets the top post in a subreddit that starts with "[Round".
    #
    # Returns a praw.objects.Submission.
    new = bot.subreddit.get_new()
    return next(post for post in new if post.title.lower().startswith("[round"))
    
  def generate_password(bot):
    # Internal: Generates a random password using the wordlist.txt file in the
    #   same directory. If the file was not found, use a random string instead.
    #
    # Returns a random string of passwords.
    try:
      words = open("wordlist.txt").read().splitlines()
      return "{:s}-{:s}-{:s}".format(sample(words),
                                     sample(words),
                                     sample(words))
    except IOError:
      return base64.urlsafe_b64encode(os.urandom(30))
    
  def reset_password(bot, password=None):
    # Internal: Resets the password of the player account, determined by
    #   bot.r_player and logs into the account with the new password.
    #
    # TODO: Maybe a persistent storage like Redis.
    #
    # Returns the new password.
    newpass = password or bot.generate_password()
    print("NEW PASSWORD: {:s}".format(newpass))
    bot.r_gamebot.send_message(
      bot.subreddit,
      "Password Change",
      "Password of {:s} is now {:s}".format(bot.player[0], newpass)
    )
    url = "http://www.reddit.com/api/update_password"
    data = {"curpass": bot.player[1], "newpass": newpass, "verpass": newpass}
    bot.r_player.request_json(url, data=data)
    bot.player = (bot.player[0], newpass)
    bot.r_player.login(bot.player[0], bot.player[1])
    
  def increment_flair(bot, user, curround):
    # Internal: Add the current win to the player's flair. If the player has
    #   more than 7 wins, sets the flair to "X wins", else adds the current
    #   round number to the flair.
    # TODO: Deal with "Fair Play Award"
    #
    #     user - A praw.objects.Redditor object.
    # curround - The round number that the user just won.
    #
    # Returns nothing.
    current_flair = bot.subreddit.get_flair(user)
    if current_flair is not None:
      flair_text    = current_flair["flair_text"]
      wins_format   = re.search("^(\d+) wins?$", str(flair_text),
                                re.IGNORECASE)
      rounds_format = re.findall("(\d+)", str(flair_text), re.IGNORECASE)
      
      if flair_text == "" or flair_text == None:
        bot.subreddit.set_flair(user, "Round {:d}".format(curround))
      elif wins_format:
        wins = int(wins_format.group(1))
        bot.subreddit.set_flair(user, "{:d} wins".format(wins + 1))
      elif rounds_format:
        rounds = len(rounds_format)
        if rounds >= 7:
          bot.subreddit.set_flair(user, "{:d} wins".format(rounds + 1))
        else:
          bot.subreddit.set_flair(user,
                                  "{:s}, {:d}".format(flair_text, curround))
    
  def winner_comment(bot, post):
    # Internal: Get the comment that gave the correct answer (because it was
    #   replied with "+correct" by the r_player account).
    #
    # post - A praw.objects.Submission object.
    #
    # Returns a praw.objects.Comment.
    comments = praw.helpers.flatten_tree(post.comments)
    for comment in comments:
      if (comment.author == bot.r_player.user and
          "+correct" in comment.body and
          not comment.is_root):
        return bot.r_gamebot.get_info(thing_id=comment.parent_id)
    
  def already_replied(bot, comment):
    # Internal: Says whether the given comment already has a reply from the
    #   bot. This is meant to be used as a backup to avoid granting the same
    #   player two wins.
    #   
    # comment - The comment to check the replies to.
    #
    # Returns a Boolean.
    for reply in winner_comment.replies:
      if reply.author == bot.r_gamebot.user:
        return True
    
  def warn_nopost(bot, op=None):
    # Internal: Warn the account and the op, if possible, that the account will
    #   be reset if he doesn't create a post in 30 minutes.
    #
    # op - An optional other person who holds the account.
    #
    # Returns nothing.
    subject = "You haven't submitted a post!"
    text    = dedent("""\
              It seems that an hour has passed since you won the last round.
              Please upload a post in the next 30 minutes, or else your account
              will be reset.
              """)
    if op:
      bot.r_gamebot.send_message(op, subject, text)
    bot.r_gamebot.send_message(bot.r_player.user, subject, text)
    
  def warn_noanswer(bot, op=None):
    # Internal: Warn the account and the op, if possible, that the account will
    #   be reset if his question isn't answered in 30 minutes.
    #
    # op - An optional other person who holds the account.
    #
    # Returns nothing.
    subject = "You haven't gotten an answer!"
    text    = dedent("""\
              It seems that 90 minutes have passed since you submitted your
              round. If no answer has been marked as correct in the next 30
              minutes, the account will be reset. Try giving hints, or if you
              already gave out a few hints, try and make them easier.
              """)
    if op:
      bot.r_gamebot.send_message(op, subject, text)
    bot.r_gamebot.send_message(bot.r_player.user, subject, text)
    
  def create_challenge(bot, run=True):
    # Internal: Reset the password and have the bot start a random challenge
    #   from the challenges.txt file.
    #
    # run - Whether or not to run the challenge after creating it.
    #   
    # Returns nothing.
    bot.reset_password()
    challenges = open("challenges.txt").read().splitlines()
    answer, address, *hints = sample(challenges).split("|")
    query = ("https://maps.googleapis.com/maps/api/streetview?size=640x640&" \
            "location={:s}&sensor=false").format(address)
    path  = "tmp/{:s}".format(address)
    urlretrieve(query, path)
    link = bot.imgur.upload_image(path, title="PictureGame Challenge").link
    newround = int(re.search("^\[round (\d+)",
                             bot.latest_round().title.lower()).group(1)) + 1
    post = bot.r_player.submit(
        bot.subreddit,
        ("[Round {:d}] [Bot] In which iconic location was this Google Street-" \
        "View image taken?").format(newround),
        url=link)
    if run:
      bot.run_challenge(post, answer)
    else:
      return (post, answer)
    
  def run_challenge(bot, post, answer):
    # Internal: Runs the challenge given on the Submission object. When the
    #   answer was found somewhere in the comments, the bot replies with
    #   "+correct" and ends itself.
    #
    #   post - A praw.objects.Submission object to run on.
    # answer - A string to look for in the comments.
    #   
    # Returns nothing.
    firsthint = secondhint = giveaway = None
    while True:
      post.refresh()
      comments = praw.helpers.flatten_tree(post.comments)
      for comment in comments:
        if answer.lower() in comment.body.lower():
          print("CORRECT ANSWER - {:s}".format(answer))
          comment.reply("+correct")
          return
        else:
          if bot.minutes_passed(post, 30) and not firsthint:
            firsthint = post.add_comment(hints[0])
          if bot.minutes_passed(post, 60) and not secondhint:
            secondhint = post.add_comment(hints[1])
          if minutes_passed(post, 90) and not giveaway:
            giveaway = post.add_comment(hints[2])
      sleep(15)
    
  def minutes_passed(bot, thing, minutes):
    # Internal: Returns True if said minutes have passed since the creation
    #   of said thing.
    # 
    #   thing - An object with a 'created_utc' attribute.
    # minutes - Number of minutes to have passed.
    # 
    # Returns a Boolean.
    return time.time() > (thing.created_utc + (minutes*60))
    
  def win(bot, comment):
    # Internal: So somebody got the right answer. First, add a win to his
    #   flair. Then, congratulate the winner and send him the resetted
    #   password via private message.
    #
    # comment - The winning comment.
    # 
    # Regrets nothing.
    comment.reply(dedent("""\
    Congratulations, that was the correct answer! Please continue the game as
    soon as possible. You have been PM'd the instructions for continuing the
    game.
    """)).distinguish()
    bot.reset_password()
    curround = int(re.search("^\[round (\d+)",
                             comment.submission.title.lower())
                   .group(1))
    bot.increment_flair(comment.author, curround)
    bot.subreddit.set_flair(comment.submission, "ROUND OVER")
    bot.append_to_leaderboard(comment.author, curround)
    subject  = "Congratulations, you can post the next round!"
    text     = dedent("""\
               The password for /u/{:s} is `{:s}`.
               **DO NOT CHANGE THIS PASSWORD.**
               It will be automatically changed once someone solves your
               challenge. Post the next round and reply to the first correct
               answer with "+correct". The post title should start with
               "[Round {:d}]". Please put your post up as soon as possible.
               \n\nIf you need any help with hosting the round, do consult
               [the wiki](http://reddit.com/r/picturegame/wiki/hosting).
               """).format(bot.player[0], bot.player[1], curround + 1)
    bot.r_gamebot.send_message(comment.author, subject, text)
    
  def parse_leaderboard(bot, page="leaderboard"):
    # Internal: Converts the table from the /wiki/leaderboard page
    #   and converts it into a dict. It uses the html content rather than the
    #   markdown content, since it's rendered and a bit more predictable.
    #
    # page - Optional page to use instead of the default.
    #
    # Returns a dict.
    content = bot.subreddit.get_wiki_page(page).content_html
    table = ET.XML(unescape(content)).find("table").find("tbody")
    return dict((row[1].text, row[2].text.split(", ")) for row in iter(table))
    
  def create_leaderboard(bot, board):
    # Internal: Use the given dict to construct a table in markdown along with
    #   ranks and win counts for each player. The dict must be in the format:
    #   {'user1': ['1', '2', '3', ...], 'user2': ['4', '5', ...], ...}
    #
    # board - The dict to use to create the table
    #
    # Returns a String.
    table = "Rank | Username | Rounds won | Total |\n" \
            "|:--:|:--:|:--|:--:|:--:|\n"
    
    inv_map = {}
    for user, rounds in board.items():
      wins = len(rounds)
      inv_map[wins] = inv_map.get(wins, [])
      inv_map[wins].append(user)
    
    for rank, wins in enumerate(sorted(inv_map, reverse=True)):
      for user in inv_map[wins]:
        table += "{rank} | {user} | {rounds} | {total}\n".format(
            rank = rank+1, user = user,
            rounds = ", ".join(board[user]), total = wins)
    
    return table
    
  def append_to_leaderboard(bot, user, roundno, page="leaderboard"):
    # Internal: Add a user's win to the wiki page, making sure to
    #   add to the win count and change the ranking.
    #
    #    user - A Redditor object to add to the leaderboard.
    # roundno - The round that the user just won.
    #    page - The wiki page to edit.
    #
    # Returns nothing.
    board = bot.parse_leaderboard()
    board[user.name] = board.get(user.name, [])
    board[user.name].append(str(roundno))
    markdown = bot.create_leaderboard(board)
    bot.subreddit.edit_wiki_page(page, markdown,
                                 reason = "{:s} won Round {:d}".format(
                                     user.name, roundno))
    
  def run(bot):
    # Public: Starts listening in the subreddit and does its thing.
    #   My complicated logic in plain English:
    #   
    #   if POST IS UNSOLVED:
    #     if POST HAS ANSWER:
    #       send password to winner
    #       chill for a bit
    #     or else:
    #       if 90 MINUTES HAVE PASSED AND I HAVEN'T WARNED YET:
    #         pm OP that he needs to provide hints before 30 minutes
    #       if 120 MINUTES HAVE PASSED AND I WARNED YA:
    #         set the flair to UNSOLVED
    #         the bot will upload a new post next loop
    #   
    #   or else if POST HAS BEEN SOLVED:
    #     if 60 MINUTES HAVE PASSED AND I HAVEN'T WARNED YET:
    #       pm OP that he needs to put a new post up before 30 minutes
    #     if 90 MINUTES HAVE PASSED AND I WARNED YA:
    #       the bot will upload a new post
    #   
    #   or else if POST HAS BEEN KILLED (DEAD ROUND/UNSOLVED):
    #     the bot will upload a new post
    # 
    # Returns nothing, it's a looping function.
    nopost_warning   = False # Warn if the user posts nothing for an hour.
    noanswer_warning = False # Warn if not answered within 1.5 hours of posting.
    current_op       = None  # The person who owns the account. (optional)
    while True:
      try:
        latest_round   = bot.latest_round()
        winner_comment = bot.winner_comment(latest_round)
        link_flair     = latest_round.link_flair_text
        
        if link_flair is None or link_flair == "":
          nopost_warning = False
          if (winner_comment and not bot.already_replied(winner_comment)):
            print("New winner! PMing new password.")
            bot.win(winner_comment)
            current_op = winner_comment.author
            noanswer_warning = False
            sleep(60)
          else:
            if bot.minutes_passed(latest_round, 90) and not noanswer_warning:
              print("Not solved for 90 minutes. Warning.")
              bot.warn_noanswer(current_op)
              noanswer_warning = True
            if bot.minutes_passed(latest_round, 120) and noanswer_warning:
              print("Not solved for 120 minutes. Setting UNSOLVED flair.")
              bot.subreddit.set_flair(latest_round, "UNSOLVED")
              noanswer_warning = False
              latest_round.add_comment(dedent("""\
              This post has not been marked as solved for 2 hours. The password
              of the account has been reset and a new challenge has been
              created.
              """))
        elif re.search(link_flair, "ROUND OVER", re.IGNORECASE):
          if bot.minutes_passed(winner_comment, 60) and not nopost_warning:
            print("Not posted for 60 minutes. Warning.")
            bot.warn_nopost(current_op)
            nopost_warning = True
          if bot.minutes_passed(winner_comment, 90) and nopost_warning:
            print("Not posted for 90 minutes. Taking over.")
            bot.create_challenge()
            nopost_warning = False
            current_op = None
        elif re.search(link_flair, "DEAD ROUND|UNSOLVED", re.IGNORECASE):
          print("DEAD ROUND/UNSOLVED flair detected. Taking over.")
          bot.create_challenge()
          noanswer_warning = False
          current_op = None
        
      except requests.exceptions.HTTPError as error:
        if error.code in [429, 500, 502, 503, 504]:
          print(("Reddit is down (error {:d})," \
                "sleeping for 5 minutes").format(error.code))
          time.sleep(300)
          pass
        else:
          raise
      except praw.errors.RateLimitExceeded as error:
        print("Ratelimit: {:d} seconds".format(error.sleep_time))
        time.sleep(error.sleep_time)
        pass
      except KeyboardInterrupt:
        print("CURRENT PASSWORD: {:s}".format(bot.player[1]))
        sys.exit(0)

if __name__ == "__main__":
  picturegame = PictureGameBot(subreddit="PictureGame")
  print(picturegame.create_leaderboard(picturegame.parse_leaderboard()))