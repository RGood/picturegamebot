"""
PictureGameBot by /u/Mustermind
Requested by /u/malz_ for /r/PictureGame
"""

import praw, os, re, base64, time
from random import choice as sample

import warnings
warnings.filterwarnings("ignore", category=ResourceWarning) 

class PictureGameBot:
  version = "0.1"
  user_agent = "/r/PictureGame Bot"
  
  def __init__(bot, gamebot=(None, None), player=(None, None), subreddit="PictureGame"):
    # Public: Logs into the bot and the player account.
    # 
    # gamebot - A tuple of username and password for the bot account.
    # player  - A tuple of username and password for the picturegame account.
    #           This is used to reset the password.
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
    
  def latest_post(bot):
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
  
  def reset_password(bot):
    # Internal: Resets the password of the player account, determined by
    #   bot.r_player and logs into the account with the new password.
    #
    # Returns the new password.
    newpass = bot.generate_password()
    url = "http://www.reddit.com/api/update_password"
    data = {"curpass": bot.player[1], "newpass": newpass, "verpass": newpass}
    bot.r_player.request_json(url, data=data)
    bot.r_player.login(bot.player[0], newpass)
    return newpass
  
  def increment_flair(bot, user):
    # Internal: If the flair is in the format "X wins", it increments the value
    #   and if the player doesn't have a flair, it sets his flair to "1 win".
    #
    # Returns nothing.
    current_flair = bot.subreddit.get_flair(user)
    if current_flair is not None:
      flair_text = current_flair["flair_text"]
      flair_match = re.search("(\d+) wins?", str(flair_text), re.IGNORECASE)
      if flair_text == "" or flair_text == None:
        bot.subreddit.set_flair(user, "1 win")
      if flair_match:
        wins = int(flair_match.group(1))
        bot.subreddit.set_flair(user, "{:d} wins".format(wins + 1))
      
  def winner_comment(bot, post):
    # Internal: Get the comment that gave the correct answer (because it was
    #   replied with "+correct" by the r_player account.
    #
    # Returns a praw.objects.Comment.
    comments = praw.helpers.flatten_tree(post.comments)
    for comment in comments:
      if (comment.author == bot.r_player.user and
          "+correct" in comment.body and not comment.is_root):
        return r.get_info(thing_id=comment.parent_id)
  
  def is_dead(bot, post):
    # Internal: A post is dead if it hasn't been solved for 5 hours or if the
    #   moderators mark it as dead. This could be because the challenge was too
    #   subjective or too vague. This can be done by giving the post a
    #   "Dead Round" flair.
    #
    # Returns a Boolean.
    if bot.winner_comment(post) is not None and time.time() > (post.created_utc + 5*60*60):
      return True
    if post.link_flair_text.lower() == "dead round":
      return True
    return False
  
  def run(bot):
    # Public: Starts listening in the subreddit and does its thing.
    # 
    # Returns nothing, it's a looping function.
    latest_round = ""
    is_dead      = False
    while True:
      "Yo"

if __name__ == "__main__":
  PictureGameBot(subreddit="")
