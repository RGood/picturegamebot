"""
PictureGameBot by /u/Mustermind
Requested by /u/malz_ for /r/PictureGame

Pretty much my magnum opus when it comes to my bot-making skills.
"""

import praw, os, re, base64, pyimgur, sys
from time import time
from textwrap import dedent
from random import choice as sample
from multiprocessing import Process
from urllib.request import urlretrieve

import warnings
warnings.filterwarnings("ignore", category=ResourceWarning) 

class PictureGameBot:
  version = "0.3"
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
    # Returns a PictureGameBot
    bot.gamebot   = (os.environ.get("REDDIT_USERNAME", gamebot[0]),
                     os.environ.get("REDDIT_PASSWORD", gamebot[1]))
    bot.r_gamebot = praw.Reddit("%{:s}, v%{:s}".format(bot.user_agent, bot.version))
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
    latest_post = next(post for post in new if post.title.lower().startswith("[round"))
    return latest_post
    
  def generate_password(bot):
    # Internal: Generates a random password using the wordlist.txt file in the
    #   same directory. If the file was not found, use a random string instead.
    #
    # Returns a random string of passwords.
    try:
      words = open("wordlist.txt").read().splitlines()
      return "{:s}-{:s}-{:s}".format(sample(words), sample(words), sample(words))
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
    bot.r_player.login(bot.player[0], newpass)
    return newpass
    
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
      wins_format   = re.search("^(\d+) wins?$", str(flair_text), re.IGNORECASE)
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
          bot.subreddit.set_flair(user, "{:s}, {:d}".format(flair_text, curround))
    
  def winner_comment(bot, post):
    # Internal: Get the comment that gave the correct answer (because it was
    #   replied with "+correct" by the r_player account.
    #   
    # post - A praw.objects.Submission object.
    #
    # Returns a praw.objects.Comment.
    comments = praw.helpers.flatten_tree(post.comments)
    for comment in comments:
      if (comment.author == bot.r_player.user and
          "+correct" in comment.body and not comment.is_root):
        return bot.r_gamebot.get_info(thing_id=comment.parent_id)
    
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
    
  def create_challenge(bot):
    # Internal: Reset the password and have the bot start a random challenge
    #   from the challenges.txt file.
    #   
    # Returns nothing. It starts its own mini loop.
    bot.reset_password()
    challenges = open("challenges.txt").read().splitlines()
    args = sample(challenges).split("|")
    p = Process(target=bot.run_challenge, args=(args[0], args[1], args[2:]))
    p.start()
    
  def run_challenge(location, address, hints):
    # Internal: Acts as a player and creates a post asking for the city of a
    #   street view image from the location.
    # 
    # location - The answer to look for in the comments.
    #  address - The query to use in the street view API.
    #    hints - The hints to provide periodically until the answer is found.
    #
    # Returns nothing.
    query = ("https://maps.googleapis.com/maps/api/streetview?size=640x640&" \
            "location={:s}&sensor=false").format(address)
    path  = "tmp/{:s}".format(address)
    urlretrieve(query, path)
    link = bot.imgur.upload_image(path, title="PictureGame Challenge").link
    newround = int(re.search("^[Round (\d+)",
                             bot.latest_round().title,
                             re.IGNORECASE).group(1)) + 1
    post = bot.r_player.submit(bot.subreddit,
      ("[Round {:d}][Bot] From which iconic location is this Google Street-" \
      "View image?").format(newround), url=link)
    
    firsthint = secondhint = giveaway = False
    while True:
      comments = praw.helpers.flatten_tree(post.comments)
      for comment in comments:
        if location.lower() in comment.body.lower():
          comment.reply("+correct")
          sys.exit(0)
        else:
          if bot.minutes_passed(post, 30) and not firsthint:
            post.add_comment(hints[0])
            firsthint = True
          if bot.minutes_passed(post, 60) and not secondhint:
            post.add_comment(hints[1])
            secondhint = True
          if minutes_passed(post, 90) and not giveaway:
            post.add_comment(hints[2])
            giveaway = True
    
  def minutes_passed(bot, thing, minutes):
    # Internal: Returns True if said minutes have passed since the creation
    #   of said thing.
    # 
    #   thing - An object with a 'created_utc' attribute.
    # minutes - Number of minutes to have passed.
    # 
    # Returns a Boolean.
    return time() > (thing.created_utc + (minutes*60))
    
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
    newpass  = bot.reset_password()
    curround = int(re.search("^\[Round (\d+)",
                             comment.submission.title,
                             re.IGNORECASE).group(1))
    bot.increment_flair(comment.author, curround)
    bot.subreddit.set_flair(comment.submission, "ROUND OVER")
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
               """).format(bot.player[0], newpass, curround + 1)
    bot.r_gamebot.send_message(comment.author, subject, text)
    
  def run(bot):
    # Public: Starts listening in the subreddit and does its thing.
    # TODO: More here.
    # 
    # Returns nothing, it's a looping function.
    latest_won       = None  # The latest post that was answered and dealt with
    current_op       = None  # The person who owns the account.
    warning_nopost   = False # Warn if the user posts nothing for an hour.
    warning_noanswer = False # Warn if not answered within 1 hour of posting.
    while True:
      latest_round = bot.latest_round()
      winner_comment = bot.winner_comment(latest_round)
      latest_round_flair = latest_round.link_flair_text
      if (latest_round == latest_won or
          (latest_round_flair and
           (latest_round_flair == "round over" or
           latest_round_flair == "dead round"))):
        if bot.minutes_passed(winner_comment, 60) and not warning_nopost:
          bot.warn_nopost(current_op)
          warning_nopost = True
        if bot.minutes_passed(winner_comment, 90):
          bot.create_challenge()
          current_op = bot.r_player.user
      else:
        if winner_comment:
          if not any(reply.author == bot.r_gamebot.user for reply in winner_comment.replies):
            bot.win(winner_comment)
            latest_won = latest_round
            current_op = winner_comment.author
            warning_nopost   = False
            warning_noanswer = False
        else:
          if bot.minutes_passed(latest_round, 90) and not warning_noanswer:
            bot.warn_noanswer(current_op)
            warning_noanswer = True
          if (bot.minutes_passed(latest_round, 120) or 
              latest_round_flair and latest_round_flair == "dead round"):
            bot.subreddit.set_flair(comment.submission, "DEAD ROUND")
            bot.create_challenge()
            current_op = bot.r_player.user
            latest_round.add_comment(dedent("""\
            This round hasn't been solved for 2 hours! The game account has
            been reset and a new challenge has been created.
            """)).distiguish()

if __name__ == "__main__":
  PictureGameBot(subreddit="ModeratorApp").run()
