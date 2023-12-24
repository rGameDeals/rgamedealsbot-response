import sqlite3
import time
import praw
import prawcore
import requests
import os
import datetime
import calendar
import logging
import re
import dateparser
import yaml
import pymysql

os.environ['TZ'] = 'UTC'

if 'MYSQL_HOST' in os.environ:
  con = pymysql.connect(
    host=os.environ['MYSQL_HOST'],
    user=os.environ['MYSQL_USER'],
    passwd=os.environ['MYSQL_PASS'],
    db=os.environ['MYSQL_DB']
)

REDDIT_CID=os.environ['REDDIT_CID']
REDDIT_SECRET=os.environ['REDDIT_SECRET']
REDDIT_USER = os.environ['REDDIT_USER']
REDDIT_PASS = os.environ['REDDIT_PASS']
REDDIT_SUBREDDIT= os.environ['REDDIT_SUBREDDIT']
AGENT="python:rGameDeals-response:2.0b (by dgc1980)"

reddit = praw.Reddit(client_id=REDDIT_CID,
                     client_secret=REDDIT_SECRET,
                     password=REDDIT_PASS,
                     user_agent=AGENT,
                     username=REDDIT_USER)
subreddit = reddit.subreddit(REDDIT_SUBREDDIT)

apppath='/storage/'

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(message)s',
                    datefmt='%m-%d %H:%M')

#logging.basicConfig(level=logging.DEBUG,
#                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
#                    datefmt='%m-%d %H:%M')

class Error(Exception):
    """Base class"""
    pass

class LinkError(Error):
    """Could not parse the URL"""
    pass

# make an empty file for first run
f = open(apppath+"postids.txt","a+")
f.close()

def get_last_tuesday(for_month):
    r = dateparser.parse(for_month)
    year = r.year
    month = r.month
    day = r.day

    last_date = calendar.monthrange(year, month)[1]
    full_end_date = dateparser.parse(f"{last_date}/{month}/{year} UTC")
    lastTuesday = full_end_date
    oneday = datetime.timedelta(days=1)

    while lastTuesday.weekday() != calendar.TUESDAY:
        lastTuesday -= oneday


    start_date_str = lastTuesday.strftime('%a, %d %B %Y ')
    return start_date_str

def getepicexpiry(epicurl):
  headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36'}
  cookies = {
                'wants_mature_content': '1',
                'birthtime': '-2148631199',
                'lastagecheckage': '1-0-1902' }
  r = requests.get(epicurl, headers=headers, cookies=cookies )

  if re.search('"endDate":"([\w\d\-\;\:\.]+)","di',r.text):
    match1 = re.search('"endDate":"(\S+)","di', r.text)
    enddate= dateparser.parse( "" + match1.group(1)  , settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'US/Pacific','TO_TIMEZONE': 'UTC' } )
    return time.mktime( enddate.timetuple() )
  return


def getsteamexpiry(steamurl):
  headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36'}
  cookies = {
                'wants_mature_content': '1',
                'birthtime': '-2148631199',
                'lastagecheckage': '1-0-1902' }
  r = requests.get(steamurl, headers=headers, cookies=cookies )
  # Offer ends 13 June</p>
  if re.search("\$DiscountCountdown", r.text) is not None:
    match1 = re.search("\$DiscountCountdown, ([\d]+)", r.text)
    return match1.group(1)
  elif re.search("Offer ends ([\w\ ]+)</p>", r.text) is not None:
    match1 = re.search("Offer ends ([\w\ ]+)</p>", r.text)
    enddate= dateparser.parse( "10am " + match1.group(1)  , settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'US/Pacific','TO_TIMEZONE': 'UTC' } )
    return time.mktime( enddate.timetuple() )
  elif re.search("Free to keep when you get it before ([\w\:\@\ \.\,]+).\t", r.text) is not None:
    match1 = re.search("Free to keep when you get it before ([\w\:\@\ \,\.]+).\t", r.text)
    enddate= dateparser.parse( "" + match1.group(1)  , settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'US/Pacific','TO_TIMEZONE': 'UTC' } )
    return time.mktime( enddate.timetuple() )
  return



def logID(postid):
    f = open(apppath+"postids.txt","a+")
    f.write(postid + "\n")
    f.close()

def respond(submission):
    logging.debug("checking submission")
    if 'MYSQL_HOST' in os.environ:
      con.ping(reconnect=True)
    #con = sqlite3.connect(apppath+'gamedealsbot.db', timeout=20)

    if 'MYSQL_HOST' in os.environ:
      cursorObj = con.cursor()
      cursorObj.execute('DELETE from schedules WHERE postid = %s', (submission.id,) )
      cursorObj.execute('INSERT into schedules(postid, schedtime) values(%s,%s)',(submission.id,(submission.created_utc + 2592000)) )
      con.commit()

    post_footer = True
    footer = """

If this deal has expired, you can reply to this comment with `{{expired trigger}}` to automatically close it.
If this deal has been mistakenly closed or has been restocked, you can open it again by replying with `{{available trigger}}`.
[^(more information)](https://www.reddit.com/r/GameDeals/wiki/gamedealsbot)
^(Note: To prevent abuse, requests are logged publicly.  Intentional abuse will likely result in a ban.)
"""

    logging.debug("loading rules")

    wikiconfig = yaml.safe_load( reddit.subreddit('gamedeals').wiki['gamedealsbot-config'].content_md )

    footer = wikiconfig['footer']
    footer = footer.replace('{{expired trigger}}',wikiconfig['expired-trigger'])
    footer = footer.replace('{{available trigger}}',wikiconfig['available-trigger'])
    logging.debug("loading rules - done")


    reply_reason = "Generic Post"
    reply_text = ""

### Find all URLS inside a .self post
    urls = []
    if not submission.author:
      logging.info("cannot find author?, skipping: " + submission.title)
      return
    if submission.author.name == "gamedealsmod":
      logging.info("gamedealsmod posted, skipping: " + submission.title)
      return
    selfpost = 0
    logging.debug("checking self")

    if submission.is_self:
        selfpost = 1
        urls = re.findall('(?:(?:https?):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+', submission.selftext)
        if len(urls) == 0:
            logging.info("NO LINK FOUND skipping: " + submission.title)
            logID(submission.id)
            return
    # remove duplicate URLs
        unique_urls = []
        for url in urls:
          if url in unique_urls:
            continue
          else:
            unique_urls.append(url)

        url = urls[0]    ### use only the first url
        if "http" not in url:
          url = "https://" + url
### get url for link post
    if not submission.is_self:
      url = submission.url
    logging.debug("checking EGS")
    if "epicgames.com" in url.lower():
      getexp = getepicexpiry(url)
      if getexp is not None:
        try:
          #con = sqlite3.connect(apppath+'gamedealsbot.db', timeout=20)
          if 'MYSQL_HOST' in os.environ:
            cursorObj = con.cursor()
            cursorObj.execute('DELETE from schedules WHERE postid = %s', (submission.id,) )
            cursorObj.execute('INSERT into schedules(postid, schedtime) values(%s,%s)',(submission.id,getexp) )
            con.commit()
          logging.info("[Steam] | " + submission.title + " | https://redd.it/" + submission.id )
          logging.info("setting up schedule: bot for: " + submission.id)
          reply_reason = "Steam Game"
          post_footer = False
          #reply_text = "^(automatic deal expiry set for " + datetime.datetime.fromtimestamp(int(getexp)).strftime('%Y-%m-%d %H:%M:%S') + " UTC)\n\n"
        except:
          pass

      if "free" in submission.title.lower():
        postdate = dateparser.parse( str(submission.created_utc) , settings={'TO_TIMEZONE': 'US/Pacific', 'TIMEZONE': 'UTC' } )


        if (  wikiconfig['egs-daily'] == "true" and ( postdate.hour < 8 or postdate.hour > 9 ) )     or     ( wikiconfig['egs-daily'] == "false" and ( postdate.weekday() == 3 and postdate.hour < 8 ) ):

######### changed the below to work based on wiki config.
#        if postdate.hour < 8 or postdate.hour > 9: # used for xmas rule, before being permanently disabled via AM to block community posting due to excessive need to moderate
#        if postdate.weekday() == 3 and postdate.hour < 8: # removed for EGS's 15 days of games to make the rule more active


          logging.info( "removing early EGS post | https://redd.it/" + submission.id )
          reply = "* We require a deal to be live before posting a submission."
          reply = "* Either this deal has already been submitted,\n\n* Or this deal has been submitted before it is live."
          comment = submission.reply(body="Unfortunately, your submission has been removed for the following reasons:\n\n" +
          reply +
          "\n\nI am a bot, and this action was performed automatically. Please [contact the moderators of this subreddit](https://www.reddit.com/message/compose/?to=/r/GameDeals) if you have any questions or concerns."
          )
          submission.mod.remove()
          comment.mod.distinguish(sticky=True)
          #logID(submission.id)
          #return

    account_flag = 0
    if re.search("//(\S+)\.itch.io", url) is not None:
      logging.info("checking itch.io")
      search1 = re.search( "//(\S+)\.itch.io" , url)
      match1 = search1.group(1)
      profile_url = "https://itch.io/profile/" + match1
      profile_page = requests.get(profile_url)
      pp1 = re.search( 'A member registered <abbr title="([\w\d\ \:\@]+)">' , profile_page.text)
      if pp1:
          pm1 = pp1.group(1)
          tm = dateparser.parse( pm1, settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'UTC', 'TO_TIMEZONE': 'UTC'} )
          tm2 = time.mktime( tm.timetuple() )
          ct = (int(time.time()) - int( tm2 )) / 86400
          logging.info("user created " + str(ct) + " days ago")
          if ct < int(wikiconfig['itch-creation-days']):
            #submission.mod.remove()
            account_flag = 1
            submission.report('new itch.io account.')
            #reddit.subreddit('modgamedeals').message(subject='suspected spam/virus account for itch.io.', message='suspected spam/virus account for itch.io.  https://redd.it/' + submission.id)
            #logID(submission.id)
            #return

    if re.search("//(\S+)\.itch.io", url) is not None and account_flag == 0:
      logging.info("checking itch.io")
      game_page = requests.get(url)
      pp1 = re.search( 'Published</td><td><abbr title="([\w\d\ \:\@]+)">' , game_page.text)
      if pp1:
          pm1 = pp1.group(1)
          tm = dateparser.parse( pm1, settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'UTC', 'TO_TIMEZONE': 'UTC'} )
          tm2 = time.mktime( tm.timetuple() )
          ct = (int(time.time()) - int( tm2 )) / 86400
          logging.info("game published " + str(ct) + " days ago")
          if ct < int(wikiconfig['itch-game-publish-days']):
            submission.report('new itch.io submission.')
            #submission.mod.remove()
            #reddit.subreddit('modgamedeals').message(subject='suspected spam/virus game for itch.io.', message='suspected spam/virus game for itch.io.  https://redd.it/' + submission.id)
            #logID(submission.id)
            #return

    if re.search("store.steampowered.com/(sub|app)", url) is not None:
     logging.debug("checking Steam")
     if submission.author_flair_css_class is not None and submission.is_self:
       return
     r = requests.get( url )


     getexp = getsteamexpiry( url )
     if getexp is not None:
       try:
         #con = sqlite3.connect(apppath+'gamedealsbot.db', timeout=20)
         if 'MYSQL_HOST' in os.environ:
           cursorObj = con.cursor()
           cursorObj.execute('DELETE from schedules WHERE postid = %s', (submission.id,) )
           cursorObj.execute('INSERT into schedules(postid, schedtime) values(%s,%s)',(submission.id,getexp) )
           con.commit()
         logging.info("[Steam] | " + submission.title + " | https://redd.it/" + submission.id )
         logging.info("setting up schedule: bot for: " + submission.id)
         reply_reason = "Steam Game"
         post_footer = False
         #reply_text = "^(automatic deal expiry set for " + datetime.datetime.fromtimestamp(int(getexp)).strftime('%Y-%m-%d %H:%M:%S') + " UTC)\n\n"
       except:
         pass


     if re.search("WEEK LONG DEAL", r.text) is not None:
       today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
       monday = today - datetime.timedelta(days=today.weekday())
       datetext = monday.strftime('%Y%m%d')
       #con = sqlite3.connect(apppath+'gamedealsbot.db', timeout=20)

       if 'MYSQL_HOST' in os.environ:
         cursorObj = con.cursor()
         cursorObj.execute('SELECT * FROM weeklongdeals WHERE week = %s', (datetext,) )
       rows = cursorObj.fetchall()
       if len(rows) == 0:
         removereason = "* It appears to be a part of the Weeklong deals. \n\nAs there are multiple games on sale, please post a thread with more games in the title [with this link](https://store.steampowered.com/search/?filter=weeklongdeals).\n\nIf you are the developer or publisher of this game, please leave a detailed disclosure as a top level comment as per [Rule 9](https://www.reddit.com/r/GameDeals/wiki/rules#wiki_9._developers_and_publishers), then [contact the mods for approval](https://www.reddit.com/message/compose?to=%2Fr%2FGameDeals)."
       else:
         removereason = "* It appears to be a part of the [Weeklong deals](https://redd.it/" + rows[0][2] + "). \n\nAs there are multiple games on sale, please include a comment within the existing thread to discuss this deal.\n\nIf you are the developer or publisher of this game, please leave a detailed disclosure as a top level comment as per [Rule 9](https://www.reddit.com/r/GameDeals/wiki/rules#wiki_9._developers_and_publishers), then [contact the mods for approval](https://www.reddit.com/message/compose?to=%2Fr%2FGameDeals)."
       comment = submission.reply(body="Unfortunately, your submission has been removed for the following reasons:\n\n" +
            removereason +
            "\n\nI am a bot, and this action was performed automatically. Please [contact the moderators of this subreddit](https://www.reddit.com/message/compose/?to=/r/GameDeals) if you have any questions or concerns."
       )
       comment.mod.distinguish(sticky=True)
       submission.mod.remove()
       return





    logging.debug("Loading Notes")
    try:
      rules = yaml.safe_load_all( reddit.subreddit('gamedeals').wiki['gamedealsbot-storenotes'].content_md )
    except:
      rules = working_rules
    working_rules = rules
    logging.debug("Notes Loaded")

    logging.debug("processing rules")
    for rule in rules:
      if rule is not None:
        if "match" in rule:
          if re.search( rule['match'] , url ):
            if "match-title" not in rule or re.search( rule['match-title'] , submission.title.lower() ):
              if "dontmatch" not in rule or not re.search( rule['dontmatch'] , url ):
                #print(rule)
                if "disabled" not in rule or rule['disabled'] == False:
                  if "type" not in rule or ( "type" in rule and (rule['type'] == "link" and selfpost == 0) or (rule['type'] == "self" and selfpost == 1) or rule['type'] == "any") :
                    if "reply_reason" in rule:
                      reply_reason = rule['reply_reason']
                    if "reply" in rule:
                      reply_text = rule['reply']
                      reply_text = reply_text.replace('{{last_tuesday}}', get_last_tuesday("This Month UTC") )
                    if "match-group" in rule:
                      search1 = re.search( rule['match'] , url)
                      match1 = search1.group(rule['match-group'])
                      reply_text = reply_text.replace('{{match}}', match1)

    logging.debug("processing rules - done")

    logging.debug("posting reply")
    ANNOUCEMENT=wikiconfig['announcement-enable']
    if post_footer:
      if ANNOUCEMENT == True:
        reply_text = wikiconfig['announcement'] + "\n\n*****\n\n"+reply_text
      if reply_text != "":
        comment = submission.reply(body=reply_text+"\n\n*****\n\n"+footer)
      else:
        comment = submission.reply(body=footer)
      comment.mod.distinguish(sticky=True)
      logging.info("Replied to: " + submission.title + "   Reason: " + reply_reason)
    else:
      if ANNOUCEMENT  == True:
        reply_reason = "posting annoucement"
        postcomment = wikiconfig['announcement'] + "\n\n*****\n\n" + wikiconfig['announcement-only-footer']
        comment = submission.reply(body=postcomment)
        comment.mod.distinguish(sticky=True)
        logging.info("Replied to: " + submission.title + "   Reason: " + reply_reason)

    logID(submission.id)
    return

#submission = reddit.submission("qiixoa")
#submission = reddit.submission("qijjlf")

#submission = reddit.submission("vx9z83")
#respond( submission )
#exit()



while True:
    try:
        logging.info("Initializing bot...")
        for submission in subreddit.stream.submissions(pause_after=0):
         if submission:
            if submission.created < int(time.time()) - 86400:
                continue
            if submission.title[0:1].lower() == "[" or submission.title[0:1].lower() == "[":


                if submission.id in open(apppath+'postids.txt').read():
                    continue
                #logging.info("Week: "+time.strftime('%Y%W'))
                #logging.info("Day: "+time.strftime('%Y%m%d'))
                #logging.info("User: "+submission.author.name)

                donotprocess=False

                ### handle weeklong deals
                if re.search("steampowered.com.*?filter=weeklongdeals", submission.url) is not None:
                  #con = sqlite3.connect(apppath+'gamedealsbot.db', timeout=20)
                  today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                  monday = today - datetime.timedelta(days=today.weekday())
                  datetext = monday.strftime('%Y%m%d')
                  if 'MYSQL_HOST' in os.environ:
                    cursorObj = con.cursor()
                    cursorObj.execute('SELECT * FROM weeklongdeals WHERE week = %s', (datetext,) )
                    rows = cursorObj.fetchall()
                    if len(rows) == 0:
                      today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                      monday = today - datetime.timedelta(days=today.weekday())
                      cursorObj.execute('INSERT INTO weeklongdeals (week, post) VALUES (%s, %s)', (monday.strftime('%Y%m%d'), submission.id))
                      con.commit()


                ###

### Weekly Post Limit
#                if 0 > 0:
#                  currentweek = time.strftime('%Y%W')
#                  #con = sqlite3.connect(apppath+'gamedealsbot.db', timeout=20)
#                  cursorObj = con.cursor()
#                  cursorObj.execute('SELECT * FROM weeklyposts WHERE username = %s AND currentweek = %s'  , (submission.author.name,currentweek))
#                  rows = cursorObj.fetchall()
#                  if len(rows) == 0:
#                    cursorObj.execute('INSERT INTO weeklyposts(username, postcount, currentweek) VALUES(%s, 1, %s)',(submission.author.name,currentweek)    )
#                    con.commit()
#                  else:
#                    curcount = rows[0][2]
#                    #if int(curcount) > int(Config.WeeklyPostLimit):
#                    if 0 > 0:
#                      donotprocess=True
#                      logging.info(submission.author.name+' is over their weekly post limit')
#                      submission.mod.remove()
#                      comment = submission.reply("Thank you for your submission, but you have reached your weekly post limit\n\n^^^^^\n\nYou may contact the modderators if you feel you are being picked on")
#                      comment.mod.distinguish(sticky=True)
#                    else:
#                      curcount=curcount+1
#                      cursorObj.execute("UPDATE weeklyposts SET postcount = %s WHERE id = %s', (str(curcount),str(rows[0][0])) )
#                      con.commit()
#                  #con.close()
###


### Daily Post Limit
#                if 0 > 0:
#                  currentday = time.strftime('%Y%m%d')
#                  con = sqlite3.connect(apppath+'gamedealsbot.db', timeout=20)
#                  cursorObj = con.cursor()
#                  cursorObj.execute('SELECT * FROM dailyposts WHERE username = "'+submission.author.name+'" AND currentday = '+currentday)
#                  rows = cursorObj.fetchall()
#                  if len(rows) == 0:
#                    cursorObj.execute('INSERT INTO dailyposts(username, postcount, currentday) VALUES("'+submission.author.name+'",1,'+currentday+')')
#                    con.commit()
#                  else:
#                    curcount = rows[0][2]
#                    #if int(curcount) > int(Config.DailyPostLimit):
#                    if 0 > 0:
#                      donotprocess=True
#                      logging.info(submission.author.name+' is over their daily post limit')
#                      submission.mod.remove()
#                      comment = submission.reply("Thank you for your submission, but you have reached your daily post limit\n\n^^^^^\n\nYou may contact the modderators if you feel you are being picked on")
#                      comment.mod.distinguish(sticky=True)
#                    else:
#                      curcount=curcount+1
#                      cursorObj.execute("UPDATE dailyposts SET postcount = " + str(curcount) + ' WHERE id = ' + str(rows[0][0]))
#                      con.commit()
#                  con.close
###




                for top_level_comment in submission.comments:
                    try:
                        if top_level_comment.author and top_level_comment.author.name == REDDIT_USER:
                            logID(submission.id)
                            break
                    except AttributeError:
                        pass
                else: # no break before, so no comment from GDB
                    if not donotprocess:
                      respond(submission)
                      continue


    except prawcore.exceptions.ServerError:
       logging.info('server error, sleeping 20 seconds')
       time.sleep(20)

    except prawcore.exceptions.TooManyRequests:
       logging.info('api limit hit, reddit changes not affecting moderation bots at all. lol........')
       time.sleep(10)
    except prawcore.exceptions.ResponseException:
       logging.info('server error')
       time.sleep(20)

    #except (prawcore.exceptions.RequestException, prawcore.exceptions.ResponseException):
    #    logging.info("Error connecting to reddit servers. Retrying in 1 minute...")
    #    time.sleep(60)

    except praw.exceptions.APIException:
        logging.info("Rate limited, waiting 5 seconds")
        time.sleep(5)

    except Exception as err:
        logging.info("Unknown Error connecting to reddit servers. Retrying in 1 minute...")
        logging.info(f"Unexpected {err=}, {type(err)=}")
        time.sleep(60)

 
