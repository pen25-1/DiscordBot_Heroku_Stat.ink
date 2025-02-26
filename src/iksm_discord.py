import subprocess
import shutil
import asyncio
from discord.ext import commands
import discord
import requests
import json
import re
import sys
import os
import base64
import hashlib
import uuid
import time
import random
import string
import datetime
import asyncio

import basic
sys.path.append(f"{os.path.dirname(__file__)}/../splatnet2statink")  # noqa
#from iksm import call_flapg_api, get_session_token, version_NSO, A_VERSION  # noqa
A_VERSION = "1.5.10"
version_NSO = "1.11.0"

session = requests.Session()

splat_path = basic.const_paths["splat_dir"]
tmp_dir = basic.const_paths["tmp_dir"]



# ------------/ discord functions /-----------------

# make config file
async def make_config_discord(API_KEY, conifg_dir, ctx: commands.Context, print_session=False):
    USER_LANG = "ja-JP"

    try:
        post_login, auth_code_verifier = log_in_discord(A_VERSION, ctx.channel)
    except Exception as e:
        ctx.channel.send(
            f"エラーが発生しました。{e}\nもう一度`?startIksm <API KEY>`からやり直してください。")
        return
    print_content = f"リンクをクリックしてログインし, 「この人にする」ボタンを長押し(PCなら右クリック)してリンク先のURLをコピーしてください。**注意: ボタンをそのままクリックするのではありません。**"
    await ctx.channel.send(print_content)
    await ctx.channel.send(post_login)
    new_token = ""
    while new_token == "":
        try:
            await ctx.channel.send("URLをペーストしてください。キャンセルする場合は`cancel`と入力してください。")

            def check_url(msg):
                return msg.author.id == ctx.message.author.id and (msg.content.startswith("npf71b963c1b7b6d119://") or msg.content == "cancel")
            try:
                input_url = await ctx.bot.wait_for("message", check=check_url, timeout=600)
            except asyncio.TimeoutError:
                await ctx.channel.send("Timeoutです。もう一度`?startIksm <API KEY>`からやり直してください。")
                return
            if input_url.content == "cancel":
                await ctx.channel.send("Canceled.")
                return
            session_token_code = re.search('de=(.*)&', input_url.content)
            new_token = get_session_token_discord(
                session_token_code.group(1), auth_code_verifier)
        except AttributeError:
            await ctx.channel.send("不適切なURLです。\nもう一度コピーしてきてください。")
        except KeyError:  # session_token not found
            await ctx.channel.send("\niksm_sessionが見つかりませんでした。Nintendo Accountからログアウトし、もう一度はじめからやり直してください。")

    acc_name, new_cookie = await get_cookie_discord(
        new_token, USER_LANG, A_VERSION, ctx.channel)

    config_data = {"api_key": API_KEY, "cookie": new_cookie,
                   "user_lang": USER_LANG, "session_token": new_token}
    # save config
    if basic.IsHeroku:  # for Heroku
        before_config_tmp = json.loads(os.getenv("iksm_configs", "{}"))
        before_config_jsons = eval(before_config_tmp) if type(
            before_config_tmp) == str else before_config_tmp
        try:
            before_config_jsons.update({acc_name: config_data})
        except:
            before_config_jsons = {acc_name: config_data}
        json_configs = json.dumps(before_config_jsons)
        basic.update_env({"iksm_configs": json.dumps(json_configs)})
    else:  # for not Heroku
        os.makedirs(tmp_dir, exist_ok=True)
        with open(f"{tmp_dir}/{acc_name}_config.txt", "w") as f:
            f.write(json.dumps(config_data, indent=4,
                               sort_keys=True, separators=(',', ': ')))


async def auto_upload_iksm():
    # auto upload
    if basic.IsHeroku:  # for Heroku
        before_config_tmp = json.loads(os.getenv("iksm_configs", "{}"))
        before_config_jsons = eval(before_config_tmp) if type(
            before_config_tmp) == str else before_config_tmp
        for acc_name, v in before_config_jsons.items():
            if v["api_key"] in ["0"*43, "skip"]:  # API_KEY is not setted
                continue
            # make config from ENV
            with open(f"{tmp_dir}/config.txt", "w") as f:
                json.dump(v, f)
            subprocess.run(
                ["python3", f"{splat_path}/splatnet2statink.py", "-r"])
    else:  # for not Heroku
        config_names = [path for path in os.listdir(
            tmp_dir) if path.endswith("_config.txt")]
        for config_name in config_names:
            shutil.copy(f"{tmp_dir}/{config_name}", f"{tmp_dir}/config.txt")
            with open(f"{tmp_dir}/config.txt") as f:
                config_json = json.load(f)
            api_key = config_json["api_key"]
            if api_key in ["0"*43, "skip"]:  # API_KEY is not setted
                continue
            subprocess.run(
                ["python3", f"{splat_path}/splatnet2statink.py", "-r"])
        # if len(config_names)!=0:
        #	os.remove(f"{tmp_dir}/config.txt")


async def autoUploadCycle(next_time=60):
    config_path = f"{basic.const_paths['tmp_dir' if basic.IsHeroku else 'splat_dir']}/config.txt"
    if not os.path.isfile(config_path):
        with open(config_path, "w") as f:
            f.write(json.dumps({}))
    nowtime = datetime.datetime.now()
    tmp_next_time = next_time-(nowtime.minute*60 + nowtime.second) % next_time
    print(f"{datetime.datetime.now()} / Next Check Time : in {tmp_next_time} sec")
    await asyncio.sleep(tmp_next_time)

    while True:
        # for splatoon2, stat.ink
        await auto_upload_iksm()
        nowtime = datetime.datetime.now()
        tmp_next_time = next_time - \
            (nowtime.minute*60+nowtime.second) % next_time
        print(f"Next Check Time : in {tmp_next_time} sec")
        await asyncio.sleep(tmp_next_time)


# -----------/ remake functions for discord_bot /-----------


def log_in_discord(ver, ctx_channel: commands.Context.channel):
    '''Logs in to a Nintendo Account and returns a session_token.'''

    version = ver

    auth_state = base64.urlsafe_b64encode(os.urandom(36))

    auth_code_verifier = base64.urlsafe_b64encode(os.urandom(32))
    auth_cv_hash = hashlib.sha256()
    auth_cv_hash.update(auth_code_verifier.replace(b"=", b""))
    auth_code_challenge = base64.urlsafe_b64encode(auth_cv_hash.digest())

    app_head = {
        'Host':                      'accounts.nintendo.com',
        'Connection':                'keep-alive',
        'Cache-Control':             'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent':                'Mozilla/5.0 (Linux; Android 7.1.2; Pixel Build/NJH47D; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/59.0.3071.125 Mobile Safari/537.36',
        'Accept':                    'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8n',
        'DNT':                       '1',
        'Accept-Encoding':           'gzip,deflate,br',
    }

    body = {
        'state':                               auth_state,
        'redirect_uri':                        'npf71b963c1b7b6d119://auth',
        'client_id':                           '71b963c1b7b6d119',
        'scope':                               'openid user user.birthday user.mii user.screenName',
        'response_type':                       'session_token_code',
        'session_token_code_challenge':        auth_code_challenge.replace(b"=", b""),
        'session_token_code_challenge_method': 'S256',
        'theme':                               'login_form'
    }

    url = 'https://accounts.nintendo.com/connect/1.0.0/authorize'
    r = session.get(url, headers=app_head, params=body)

    post_login = r.history[0].url

    return post_login, auth_code_verifier


async def get_cookie_discord(session_token, userLang, ver, ctx_channel: commands.Context.channel):
    '''Returns a new cookie provided the session_token.'''

    version = ver

    timestamp = int(time.time())
    guid = str(uuid.uuid4())

    app_head = {
        'Host':            'accounts.nintendo.com',
        'Accept-Encoding': 'gzip',
        'Content-Type':    'application/json; charset=utf-8',
        'Accept-Language': userLang,
        'Content-Length':  '439',
        'Accept':          'application/json',
        'Connection':      'Keep-Alive',
        'User-Agent':      f'OnlineLounge/{version_NSO} NASDKAPI Android'
    }

    body = {
        'client_id':     '71b963c1b7b6d119',  # Splatoon 2 service
        'session_token': session_token,
        'grant_type':    'urn:ietf:params:oauth:grant-type:jwt-bearer-session-token'
    }

    url = "https://accounts.nintendo.com/connect/1.0.0/api/token"

    r = requests.post(url, headers=app_head, json=body)
    id_response = json.loads(r.text)

    # get user info
    try:
        app_head = {
            'User-Agent':      f'OnlineLounge/{version_NSO} NASDKAPI Android',
            'Accept-Language': userLang,
            'Accept':          'application/json',
            'Authorization':   'Bearer {}'.format(id_response["access_token"]),
            'Host':            'api.accounts.nintendo.com',
            'Connection':      'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }
    except:
        await ctx_channel.send(f"Not a valid autho ization request. Please delete config.txt and try again. \
		Error from Nintendo (in api/token step): \
		{json.dumps(id_response, indent=2)}")
        return
    url = "https://api.accounts.nintendo.com/2.0.0/users/me"

    r = requests.get(url, headers=app_head)
    user_info = json.loads(r.text)

    nickname = user_info["nickname"]

    # get access token
    app_head = {
        'Host':             'api-lp1.znc.srv.nintendo.net',
        'Accept-Language':  userLang,
        'User-Agent':       f'com.nintendo.znca/{version_NSO} (Android/7.1.2)',
        'Accept':           'application/json',
        'X-ProductVersion': f'{version_NSO}',
        'Content-Type':     'application/json; charset=utf-8',
        'Connection':       'Keep-Alive',
        'Authorization':    'Bearer',
        # 'Content-Length':   '1036',
        'X-Platform':       'Android',
        'Accept-Encoding':  'gzip'
    }

    body = {}
    try:
        idToken = id_response["access_token"]

        flapg_nso = await call_flapg_api_discord(idToken, guid, timestamp, "nso", ctx_channel)

        parameter = {
            'f':          flapg_nso["f"],
            'naIdToken':  flapg_nso["p1"],
            'timestamp':  flapg_nso["p2"],
            'requestId':  flapg_nso["p3"],
            'naCountry':  user_info["country"],
            'naBirthday': user_info["birthday"],
            'language':   user_info["language"]
        }
    #except SystemExit:
    #    return -1
    except:
        await ctx_channel.send(f"Error(s) from Nintendo: \
		{json.dumps(id_response, indent=2)} \
		{json.dumps(user_info, indent=2)}")
        return -2
    body["parameter"] = parameter

    url = "https://api-lp1.znc.srv.nintendo.net/v1/Account/Login"

    r = requests.post(url, headers=app_head, json=body)

    splatoon_token = json.loads(r.text)

    try:
        idToken = splatoon_token["result"]["webApiServerCredential"]["accessToken"]
        flapg_app = await call_flapg_api_discord(idToken, guid, timestamp, "app", ctx_channel)
    except:
        await ctx_channel.send("Error from Nintendo (in Account/Login step):" +
                         json.dumps(splatoon_token, indent=2))
        return -1

    # get splatoon access token
    try:
        app_head = {
            'Host':             'api-lp1.znc.srv.nintendo.net',
            'User-Agent':       f'com.nintendo.znca/{version_NSO} (Android/7.1.2)',
            'Accept':           'application/json',
            'X-ProductVersion': f'{version_NSO}',  # update
            'Content-Type':     'application/json; charset=utf-8',
            'Connection':       'Keep-Alive',
            'Authorization':    f'Bearer {splatoon_token["result"]["webApiServerCredential"]["accessToken"]}',
            'Content-Length':   '37',
            'X-Platform':       'Android',
            'Accept-Encoding':  'gzip'
        }
    except:
        await ctx_channel.send(f"Error from Nintendo (in Account/Login step):\

		{json.dumps(splatoon_token, indent=2)}")
        return

    body = {}
    parameter = {
        'id':                5741031244955648,
        'f':                 flapg_app["f"],
        'registrationToken': flapg_app["p1"],
        'timestamp':         flapg_app["p2"],
        'requestId':         flapg_app["p3"]
    }
    body["parameter"] = parameter

    url = "https://api-lp1.znc.srv.nintendo.net/v2/Game/GetWebServiceToken"

    r = requests.post(url, headers=app_head, json=body)
    splatoon_access_token = json.loads(r.text)

    # get cookie
    try:
        app_head = {
            'Host':                    'app.splatoon2.nintendo.net',
            'X-IsAppAnalyticsOptedIn': 'false',
            'Accept':                  'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding':         'gzip,deflate',
            'X-GameWebToken':          splatoon_access_token["result"]["accessToken"],
            'Accept-Language':         userLang,
            'X-IsAnalyticsOptedIn':    'false',
            'Connection':              'keep-alive',
            'DNT':                     '0',
            'User-Agent':              'Mozilla/5.0 (Linux; Android 7.1.2; Pixel Build/NJH47D; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/59.0.3071.125 Mobile Safari/537.36',
            'X-Requested-With':        'com.nintendo.znca'
        }
    except:
        await ctx_channel.send("Error from Nintendo (in Game/GetWebServiceToken step):" +
                         json.dumps(splatoon_access_token, indent=2))
        return

    url = "https://app.splatoon2.nintendo.net/?lang={}".format(userLang)
    r = requests.get(url, headers=app_head)

    return nickname, r.cookies["iksm_session"]

def get_session_token_discord(session_token_code, auth_code_verifier): # use for discord
    '''Helper function for log_in().'''

    app_head = {
        'User-Agent':      f'OnlineLounge/{version_NSO} NASDKAPI Android',
        'Accept-Language': 'en-US',
        'Accept':          'application/json',
        'Content-Type':    'application/x-www-form-urlencoded',
        'Content-Length':  '540',
        'Host':            'accounts.nintendo.com',
        'Connection':      'Keep-Alive',
        'Accept-Encoding': 'gzip'
    }

    body = {
        'client_id':                   '71b963c1b7b6d119',
        'session_token_code':          session_token_code,
        'session_token_code_verifier': auth_code_verifier.replace(b"=", b"")
    }

    url = 'https://accounts.nintendo.com/connect/1.0.0/api/session_token'

    r = session.post(url, headers=app_head, data=body)
    return json.loads(r.text)["session_token"]

async def get_hash_from_s2s_api_discord(id_token, timestamp, ctx_channel: commands.Context.channel): # use for discord
    '''Passes an id_token and timestamp to the s2s API and fetches the resultant hash from the response.'''

    # check to make sure we're allowed to contact the API. stop spamming my web server pls
    """config_data={}

	try:
		with open(config_path, "r") as f:
			config_data = json.loads(f.read()) # fileが存在しない場合に
		num_errors = config_data["api_errors"]
	except:
		num_errors = 0
	if num_errors >= 5:
		print("Too many errors received from the splatnet2statink API. Further requests have been blocked until the \"api_errors\" line is manually removed from config.txt. If this issue persists, please contact @frozenpandaman on Twitter/GitHub for assistance.")
		sys.exit(1)"""

    # proceed normally
    try:
        api_app_head = {'User-Agent': "splatnet2statink/{}".format(A_VERSION)}
        api_body = {'naIdToken': id_token, 'timestamp': timestamp}
        api_response = requests.post(
            "https://elifessler.com/s2s/api/gen2", headers=api_app_head, data=api_body)
        #print(api_response.ok, api_response.content)
        if not api_response.ok:
            print(api_response.text)
            await ctx_channel.send(api_response.text["error"])
            return
        #print(api_response.text)
        return json.loads(api_response.text)["hash"]
    except:
        error_message="Error from the splatnet2statink API"
        print(error_message)
        await ctx_channel.send(error_message)

        """# add 1 to api_errors in config
		config_data={}
		try:
			with open(config_path, "r") as config_file:
				config_data = json.load(config_file)
			num_errors = config_data["api_errors"]
		except:
			num_errors = 0

		num_errors += 1
		config_data["api_errors"] = num_errors

		config_file = open(config_path, "w") # from write_config()
		config_file.seek(0)
		config_file.write(json.dumps(config_data, indent=4, sort_keys=True, separators=(',', ': ')))
		config_file.close()
"""
        #sys.exit(1)


async def call_flapg_api_discord(id_token, guid, timestamp, type, ctx_channel: commands.Context.channel): # use for discord
    '''Passes in headers to the flapg API (Android emulator) and fetches the response.'''

    try:
        api_app_head = {
            'x-token': id_token,
            'x-time':  str(timestamp),
            'x-guid':  guid,
            'x-hash':  await get_hash_from_s2s_api_discord(id_token, timestamp, ctx_channel),
            'x-ver':   '3',
            'x-iid':   type
        }
        api_response = requests.get(
            "https://flapg.com/ika2/api/login?public", headers=api_app_head)
        #print(api_response.text)
        f = json.loads(api_response.text)["result"]
        return f
    except Exception as e:
        try:  # if api_response never gets set
            error_message=""
            if api_response.text:
                error_message=u"Error from the flapg API:\n{}".format(json.dumps(
                    json.loads(api_response.text), indent=2, ensure_ascii=False))
            elif api_response.status_code == requests.codes.not_found:
                error_message="Error from the flapg API: Error 404 (offline or incorrect headers)."
            else:
                error_message="Error from the flapg API: Error {}.".format(api_response.status_code)
        except:
            pass
        print(error_message)
        await ctx_channel.send(error_message)
        raise(RuntimeError(error_message))
        #sys.exit(1)

