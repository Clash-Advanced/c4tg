# Copyright (C) 2024 originalFactor
# 
# This file is part of embyHelp.
# 
# embyHelp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# embyHelp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with embyHelp.  If not, see <https://www.gnu.org/licenses/>.

# import modules
from yaml import safe_load, safe_dump
from logging import basicConfig, INFO, debug, info, warn, error, fatal
from os.path import exists, isdir
from os import environ, mkdir
from sys import exit as sexit
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters, MessageHandler
from pymongo import MongoClient
from json import dumps

# errors
NO_PROFILE_ERR = '''
ERR: WE CANNOT FIND YOUR PROFILE. PLEASE CREATE ONE FIRST.
'''
ERR_NOT_ENOUGH_ARGUMENTS = '''
ERR: Your command is not valid. Please check guide by `/start` again.
'''
ERR_PROFILE_CREATED = '''
ERR: Your nick is already chosen.
'''

# get markdowned code
def mdCode(code:str)->str:
    return f'''```
{code}
```'''

# Initialize database
conn = MongoClient(environ['C4TG_DB'] if environ.get("C4TG_DB") else input("MongoDB URI: "))
db = conn['c4tg']
users = db['users']
nicks = db['nicks']

# get admin user
admin = int(environ['C4TG_ADMIN'] if environ.get('C4TG_ADMIN') else input('Admin Telegram ID: '))

# /start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text='''
Clash Configuration Generator v0.1
Commands:
`/create` Create an profile
`/set <name> <url>`Set provider
`/rm <name>` Delete provider
`/get [nick]` Generate config
`/share <nick>` Share your profile
`/reset` Delete your profile
*`<>` means required and `[]` means optional*
Warning:
- Your subscription will be encrypted and storaged in our cloud service. If you care about it, try to deploy your own application.
GitHub Repository: https://github.com/Clash-Advanced/c4tg
- Do not share nicks publicly. Everyone can use that <nick> to access your profile.
''')

# init logger
basicConfig(
    format='%(asctime)s - [%(levelname)s] - %(name)s : %(message)s',
    level=INFO
)

# load templates
try:
    with open("subscribe_template.yaml",encoding='utf-8')as f:
        SUBTEMPLATE:dict = safe_load(f)
    with open("config_template.yaml",encoding='utf-8')as f:
        CONFTEMPLATE:dict = safe_load(f)
except FileNotFoundError as e:
    fatal(f'File Not Found: {e}')
    sexit(-1)
except UnicodeDecodeError as e:
    fatal(f'Non-UTF-8 Encoding: {e}')
else:
    info("INITIAL COMPLETED.")

# administrator
def is_admin(func):
    async def wrapper(update:Update, context:ContextTypes.DEFAULT_TYPE):
        return await func(update,context,update.effective_sender.id==admin)
    return wrapper

# fn to change many thing in a dict|list
def multiChange(source:dict|list,target:list[str|int]|None=None,value=None,td:dict|None=None)->dict|list:
    if target:
        for i in target:
            source[i]=value
    elif td:
        for k,v in td.items():
            source[k]=v
    return source

# get config by args
def getConfig(
    share:bool=False,
    cleanNS:list[str]=[],
    fastNS:list[str]=[],
    ipv6:bool=False,
    external_ui:str='',
    proxy_providers:dict={},
    tun:bool=False,
    mix:int=0,
    tproxy:int=0,
    redir:int=0,
    secret:str=''
) -> str:
    conf = CONFTEMPLATE.copy()
    if share:
        conf["allow-lan"] = True
        conf['bind-address'] = '*'
        conf['dns']['listen'] = '0.0.0.0:53'
        conf['external-controller'] = '0.0.0.0:9090'

    if cleanNS:
        multiChange(conf['dns'],['default-nameserver','fallback'],cleanNS)
        conf['dns']['nameserver-policy']['geosite:!cn']=cleanNS[0]

    if fastNS:
        conf['dns']['nameserver'] = fastNS
        conf['dns']['nameserver-policy']["geosite:cn"] = fastNS[0]

    conf['ipv6'] = conf['dns']['ipv6'] = bool(ipv6)

    conf['external-ui'] = external_ui

    for name,url in proxy_providers.items():
        conf['proxy-providers'][name+' Subscription']={
            "path": f"./provider/{'_'.join(name.strip().split())}.yaml",
            "url": url,
            **SUBTEMPLATE
        }
        for tn,ti,tm,tf in [
            ("Manual", "select", 1, 1),
            ("Fallback", "fallback", 2, 5),
            ("URL Test", "url-test", 3, 6),
            ("Load Balance", "load-balance", 4, 7)
        ]:
            conf['proxy-groups'].append({
                'name': name+' '+tn,
                'type': ti,
                'use': [name+' Subscription']
            })
            conf['proxy-groups'][tm]['proxies'].append(name+' '+tn)
            if tm!=tf:conf['proxy-groups'][tf]['proxies'].append(name+' '+tn)

    conf['tun']['enable'] = bool(tun)

    conf['mixed-port'] = mix
    conf['tproxy-port'] = tproxy
    conf['redir-port'] = redir

    conf['secret'] = secret

    return safe_dump(conf)

# handler of /get [nick] 
@is_admin
async def get(update: Update, context: ContextTypes.DEFAULT_TYPE, admin:bool):
    if context.args:
        uid = nicks.find_one({'name':context.args[0]},projection={'_id':False}).get('id',0)
    else: uid = update.effective_sender.id
    profile = users.find_one({
        "id": uid,
    },projection={'_id':False})
    if admin: await context.bot.send_message(update.effective_chat.id,dumps(profile))
    if not profile:
        await context.bot.send_message(update.effective_chat.id,NO_PROFILE_ERR)
        return
    if not(exists(f'temp/{uid}') and isdir(f'temp/{uid}')): mkdir(f'temp/{uid}')
    with open(f'temp/{uid}/config.yaml','w',encoding='utf-8')as f: f.write(getConfig(**profile['config']))
    await context.bot.send_document(update.effective_chat.id,f'temp/{uid}/config.yaml')
    await context.bot.send_message(update.effective_chat.id,'Configuration file sent.')

# handler of /set <name> <url>
@is_admin
async def set_(update:Update, context:ContextTypes.DEFAULT_TYPE, admin:bool):
    if len(context.args)!=2:
        await context.bot.send_message(update.effective_chat.id,ERR_NOT_ENOUGH_ARGUMENTS)
        return
    profile = (users.find_one({'id': update.effective_sender.id},projection={'_id':False}))
    if admin: await context.bot.send_message(update.effective_chat.id,dumps(profile))
    if not profile:
        await context.bot.send_message(update.effective_chat.id,NO_PROFILE_ERR)
        return
    users.update_one(
        {'id': update.effective_sender.id},
        {'$set':{f'config.proxy_providers.{context.args[0]}':context.args[1]}}
    )
    await context.bot.send_message(update.effective_chat.id,'Completed.')

# handler of /rm <name>
@is_admin
async def rm(update:Update, context:ContextTypes.DEFAULT_TYPE, a:bool):
    if len(context.args)!=1:
        await context.bot.send_message(update.effective_chat.id,ERR_NOT_ENOUGH_ARGUMENTS)
        return
    profile = (users.find_one({'id': update.effective_sender.id},projection={'_id':False}))
    if a: await context.bot.send_message(update.effective_chat.id,dumps(profile))
    if not profile:
        await context.bot.send_message(update.effective_chat.id,NO_PROFILE_ERR)
        return
    users.update_one(
        {'id': update.effective_sender.id},
        {'$unset':{f'config.proxy_providers.{context.args[0]}':''}}
    )
    await context.bot.send_message(update.effective_chat.id,'Completed.')

# handler of /share <nick>
@is_admin
async def share(update:Update, context:ContextTypes.DEFAULT_TYPE, a:bool):
    if not context.args:
        await context.bot.send_message(update.effective_chat.id,ERR_NOT_ENOUGH_ARGUMENTS)
        return
    profile = (nicks.find_one({'name':context.args[0]},projection={'_id':False}))
    if a: await context.bot.send_message(update.effective_chat.id,dumps(profile))
    if profile:
        await context.bot.send_message(update.effective_chat.id,ERR_PROFILE_CREATED)
        return
    nicks.insert_one({
        'id': update.effective_sender.id,
        'name': context.args[0]
    })
    await context.bot.send_message(update.effective_chat.id,'Completed.')

# handler of /reset
async def reset(update:Update, context:ContextTypes.DEFAULT_TYPE):
    nicks.delete_many({'id':update.effective_sender.id})
    users.delete_many({'id':update.effective_sender.id})
    await context.bot.send_message(update.effective_chat.id,'Successful deleted your profile. Please re-create one.')

# handler of /create
@is_admin
async def create(update:Update, context:ContextTypes.DEFAULT_TYPE, a:bool):
    profile = (users.find_one({'id':update.effective_sender.id},projection={'_id':False}))
    if a: await context.bot.send_message(update.effective_chat.id,dumps(profile))
    if profile:
        await context.bot.send_message(update.effective_chat.id,ERR_PROFILE_CREATED)
        return
    users.insert_one({
        'id': update.effective_sender.id,
        'config': {
            'proxy_providers': {}
        }
    })
    await context.bot.send_message(update.effective_chat.id,'Success.')

# handler for /getid
async def get_sender_id(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(update.effective_chat.id,f'Your Sender ID is {update.effective_sender.id}')

# Command not found handler
async def command_not_found(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(update.effective_chat.id,ERR_NOT_ENOUGH_ARGUMENTS)

# Main program
if __name__ == '__main__':
    # get telegram token
    tg_token = environ['C4TG_TOKEN'] if environ.get('C4TG_TOKEN') else input('Telegram bot key: ')
    # build application by token
    application = ApplicationBuilder().token(tg_token).build()
    # create handlers
    start_handler = CommandHandler('start', start)
    set_handler = CommandHandler('set',set_)
    rm_handler = CommandHandler('rm',rm)
    get_handler = CommandHandler('get',get)
    share_handler = CommandHandler('share',share)
    reset_handler = CommandHandler('reset',reset)
    create_handler = CommandHandler('create',create)
    unknown_handler = MessageHandler(filters.COMMAND,command_not_found)
    getid_handler = CommandHandler('getid',get_sender_id)
    # add handlers
    application.add_handlers([
        start_handler,
        set_handler,
        rm_handler,
        get_handler,
        share_handler,
        reset_handler,
        create_handler,
        getid_handler
    ])
    application.add_handler(unknown_handler)
    # run
    application.run_polling()