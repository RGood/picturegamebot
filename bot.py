"""
PictureGameBot by /u/Mustermind
Requested by /u/malz_ for /r/PictureGame

Pretty much my magnum opus when it comes to my bot-making skills.
"""

import praw, os, re, base64, time
from textwrap import dedent
from random import choice as sample

import warnings
warnings.filterwarnings("ignore", category=ResourceWarning) 

class PictureGameBot:
  version = "0.2"
  user_agent = "/r/PictureGame Bot"
  
  def __init__(bot, gamebot=(None, None), player=(None, None), subreddit="PictureGame"):
    # Public: Logs into the bot and the player account.
    # 
    # gamebot   - A tuple of username and password for the bot account.
    # player    - A tuple of username and password for the picturegame account.
    #             This is used to reset the password.
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
    # Returns the new password.
    newpass = password or bot.generate_password()
    url = "http://www.reddit.com/api/update_password"
    data = {"curpass": bot.player[1], "newpass": newpass, "verpass": newpass}
    bot.r_player.request_json(url, data=data)
    bot.r_player.login(bot.player[0], newpass)
    return newpass
    
  def increment_flair(bot, user, curround):
    # Internal: Add the current win to the player's flair. If the player has
    #   more than 7 wins, sets the flair to "X wins", else adds the current
    #   round number to the flair.
    # TODO: Deal with "Fair Play Award"
    #
    # user - A praw.objects.Redditor object.
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
        if len(rounds_format) >= 7:
          bot.subreddit.set_flair(user, "{:d} wins".format(len(rounds_format) + 1))
        elsif len(rounds_format) < 7:
          bot.subreddit.set_flair(user, flair_text + ", " + curround)
    
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
        return r.get_info(thing_id=comment.parent_id)
    
  def is_dead(bot, post):
    # Internal: A post is dead if it hasn't been solved for 5 hours or if the
    #   moderators mark it as dead. This could be because the challenge was too
    #   subjective or too vague. This can be done by giving the post a
    #   "Dead Round" flair.
    #   
    # post - A praw.objects.Submission object to check.
    #
    # Returns a Boolean.
    if bot.winner_comment(post) is not None and time.time() > (post.created_utc + 5*60*60):
      return True
    if post.link_flair_text.lower() == "dead round":
      return True
    return False
    
  def win(bot, comment):
    # Internal: So somebody got the right answer. First, add a win to his flair.
    #   Then, congratulate the winner and send him the resetted password via
    #   private message.
    #
    # comment - The winning comment.
    # 
    # Regrets nothing.
    comment.reply(dedent("""
      Congratulations, that was the correct answer! Please continue the game as
      soon as possible. You have been PM'd the instructions for continuing the
      game.
    """)).distinguish()
    newpass  = bot.reset_password()
    curround = int(re.search("^[Round (\d+)",
                             comment.submission.title,
                             re.IGNORECASE).group(1))
    bot.increment_flair(comment.author, curround)
    subject  = "Congratulations, you can post the next round!"
    text     = dedent("""
                 The password for /u/{:s} is `{:s}`.
                 **DO NOT CHANGE THIS PASSWORD.**
                 It will be automatically changed once someone solves your riddle.
                 Post the next round and reply to the first correct answer with
                 "+correct". The post title should start with "[Round {:d}]".
                 Please put your post up as soon as possible.\n\n
                 If you need any help with hosting the round, do
                 [consult the wiki](http://reddit.com/r/picturegame/wiki/hosting).
               """).format(bot.player[0], newpass, curround + 1)
    bot.r_gamebot.send_message(comment.author, subject, text)
    
  def run(bot):
    # Public: Starts listening in the subreddit and does its thing.
    # 
    # Returns nothing, it's a looping function.
    latest_won = None
    while True:
      latest_round = bot.latest_round()
      if latest_round == latest_won:
        # We're still waiting on the next post.
        
        # TODO: Notify the OP that his account is moving on without him if he
        #   doesn't post for 5 hours.
        # TODO: Notify the OP a couple of hours earlier that his account is
        #   going bye-bye soon if he doesn't post soon.
        "See comment"
      else:
        # We're still waiting on the answer.
        if bot.is_dead(latest_round):
          # The post is officially dead.
          # TODO: Move on to a better home.
          "See comment"
        else:
          winner_comment = bot.winner_comment()
          if winner_comment is not None:
            # We have an answer! Pass the account to him.
            bot.win(winner_comment)
            latest_won = latest_round

if __name__ == "__main__":
  print(PictureGameBot(subreddit="ModeratorApp").generate_password())
