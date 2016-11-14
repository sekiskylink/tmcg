#!/usr/bin/python
# Author: Samuel Sekiwere <sekiskylink@gmail.com>

import os
import sys
import web
import urllib
import logging
# import re
# import time
# from datetime import datetime
# from datetime import timedelta
import requests
import json
from web.contrib.template import render_jinja
from pagination import doquery, getPaginationString, countquery
from settings import config

filedir = os.path.dirname(__file__)
sys.path.append(os.path.join(filedir))

script_dir = os.path.split(os.path.abspath(__file__))[0]
parent_dir = os.path.abspath(os.path.join(script_dir, '..'))


class AppURLopener(urllib.FancyURLopener):
    version = "tmcg /1.0"

urllib._urlopener = AppURLopener()

logging.basicConfig(
    format='%(asctime)s:%(levelname)s:%(message)s', filename='/tmp/tmcg-web.log',
    datefmt='%Y-%m-%d %I:%M:%S', level=logging.DEBUG
)

# DB confs
db_host = config['db_host']
db_name = config['db_name']
db_user = config['db_user']
db_passwd = config['db_passwd']
db_port = config['db_port']
urls = (
    "/", "Index",
    "/info", "Info",
    "/smslogs", "Smslogs",
    "/kannelseries", "KannelSeries",
    "/campaignseries", "CampaignSeries",
    "/refresh", "Refresh",
    "/reports", "Reports",
    "/fieldcontacts", "FieldContacts",
    "/completed", "Completed",
    "/search", "Search",
    "/users", "Users",
    "/logout", "Logout",
    # webhooks
    "/steppingstones", "SteppingStone",
)

# web.config.smtp_server = 'mail.mydomain.com'
web.config.debug = False

app = web.application(urls, globals())
db = web.database(
    dbn='postgres',
    user=db_user,
    pw=db_passwd,
    db=db_name,
    host=db_host,
    port=db_port
)

store = web.session.DBStore(db, 'sessions')
session = web.session.Session(app, store, initializer={'loggedin': False})

render = render_jinja(
    'templates',
    encoding='utf-8'
)
render._lookup.globals.update(
    ses=session
)

SETTINGS = {
    'PAGE_LIMIT': 25,
}


app.notfound = lambda: web.notfound(render.missing())


def lit(**keywords):
    return keywords


def default(*args):
    p = [i for i in args if i or i == 0]
    if p.__len__():
        return p[0]
    if args.__len__():
        return args[args.__len__() - 1]
    return None


def post_request(data, url=config['default_api_uri']):
    response = requests.post(url, data=data, headers={
        'Content-type': 'application/json',
        'Authorization': 'Token %s' % config['api_token']})
    return response


def auth_user(db, username, password):
    sql = (
        "SELECT a.id, a.firstname, a.lastname, b.user_role as role "
        "FROM users a, user_roles b "
        "WHERE username = $username AND password = crypt($passwd, password) "
        "AND a.user_role = b.id AND is_active = 't'")
    # sql = (
    #     "SELECT id,first_name firstname,last_name lastname FROM "
    #     "auth_user WHERE username = '%s'")
    res = db.query(sql, {'username': username, 'passwd': password})
    # res = db.query(sql % (username))
    if not res:
        return False, "Wrong username or password"
    else:
        return True, res[0]


def require_login(f):
    """usage
    @require_login
    def GET(self):
        ..."""
    def decorated(*args, **kwargs):
        if not session.loggedin:
            session.logon_err = "Please Logon"
            return web.seeother("/")
        else:
            session.logon_err = ""
        return f(*args, **kwargs)

    return decorated


def csrf_token():
    if 'csrf_token' not in session:
        from uuid import uuid4
        session.csrf_token = uuid4().hex
    return session.csrf_token


def csrf_protected(f):
    def decorated(*args, **kwargs):
        inp = web.input()
        if not ('csrf_token' in inp and inp.csrf_token == session.pop('csrf_token', None)):
            raise web.HTTPError(
                "400 Bad request",
                {'content-type': 'text/html'},
                """Cross-site request forgery (CSRF) attempt (or stale browser form).
<a href="/"></a>.""")  # Provide a link back to the form
        return f(*args, **kwargs)
    return decorated

render._lookup.globals.update(csrf_token=csrf_token)


class Index:
    def GET(self):
        l = locals()
        del l['self']
        return render.start(**l)

    @csrf_protected
    def POST(self):
        global session
        params = web.input(username="", password="")
        username = params.username
        password = params.password
        r = auth_user(db, username, password)
        if r[0]:
            session.loggedin = True
            info = r[1]
            session.username = info.firstname + " " + info.lastname
            session.sesid = info.id
            session.role = info.role
            # requests = db.query("SELECT * FROM requests order by id desc")
            # all_requests = {}
            # for request in all_requests:
            #     all_requests[request.id] = request.submissionid
            # session.all_requests = all_requests

            l = locals()
            del l['self']
            return web.seeother("/smslogs")
        else:
            session.loggedin = False
            session.logon_err = r[1]
        l = locals()
        del l['self']
        return render.logon(**l)


class Smslogs:
    @require_login
    def GET(self):
        params = web.input(page=1)
        try:
            page = int(params.page)
        except:
            page = 1

        limit = SETTINGS['PAGE_LIMIT']
        start = (page - 1) * limit if page > 0 else 0

        dic = lit(relations='sms_stats', fields="*", criteria="", order="id desc", limit=limit, offset=start)
        res = doquery(db, dic)
        count = countquery(db, dic)
        pagination_str = getPaginationString(default(page, 0), count, limit, 2, "smslogs", "?page=")

        l = locals()
        del l['self']
        return render.smslogs(**l)


class FieldContacts:
    @require_login
    def GET(self):
        params = web.input(field="")
        field = params.field
        field_label = field.capitalize() if field else "Field Name"
        resp = """<table id="ctable" class="row-border table table-striped table-bordered">"""
        resp += """<thead><th>%s</th><th>No. of Contacts</th></thead><tbody>""" % (field_label)
        r = db.query("select * from count_by_contactfield($field);", {'field': field})
        for row in r:
            resp += "<tr><td>%s</td><td>%s</td></tr>" % (row["field"], row["count"])
        resp += "</tbody><table>"

        return resp

    @require_login
    def POST(self):
        pass


class Reports:
    @require_login
    def GET(self):
        params = web.input(page=1)
        try:
            page = int(params.page)
        except:
            page = 1

        limit = SETTINGS['PAGE_LIMIT']
        start = (page - 1) * limit if page > 0 else 0

        dic = lit(
            relations='contacts_contactgroup_counts_view', fields="*",
            criteria="name <> 'All Contacts'",
            order="name",
            limit=limit, offset=start)
        res = doquery(db, dic)
        count = countquery(db, dic)
        pagination_str = getPaginationString(default(page, 0), count, limit, 2, "ready", "?page=")

        r = db.query("select count from contacts_contactgroup_counts_view where name='All Contacts';")
        total_contacts = r[0].count

        contact_fields = db.query("select id, label from contacts_contactfield order by label;")
        campaigns = db.query("SELECT * from campaigns_view")

        l = locals()
        del l['self']
        return render.reports(**l)


class KannelSeries:
    def GET(self):
        params = web.input(id="")
        if params.id:
            rs = db.query(
                "SELECT * FROM sms_stats WHERE id = $id", {'id': params.id})
            ret = ""
            if rs:
                r = rs[0]
                # period = "For %s (Last updated: %s)" % (r['month'], r['updated'])
                incoming = "Incoming,%s,%s,%s,%s" % (r['mtn_in'], r['airtel_in'], r['africel_in'], r['utl_in'])
                outgoing = "Outgoing,%s,%s,%s,%s" % (r['mtn_out'], r['airtel_out'], r['africel_out'], r['utl_out'])
                # ret = period + "\n" + incoming + "\n" + outgoing
                ret = incoming + "\n" + outgoing
            return ret
        return ""


class CampaignSeries:
    def GET(self):
        params = web.input(campaign_id="")
        web.header('Content-Type', 'application/json')
        if params.campaign_id:
            c = db.query("SELECT name FROM campaigns_campaign WHERE id = $id", {'id': params.campaign_id})
            name = c[0]['name'] if c else ""

            rs = db.query(
                "SELECT 'Day ' || day as day, campaign_event_runs, relative_to "
                "FROM campaigns_event_contacts_view "
                "WHERE campaign_id = $campaign_id ", {'campaign_id': params.campaign_id})
            categories = []
            data = []
            relative_to = ""
            if rs:
                for r in rs:
                    categories.append(r['day'])
                    data.append(r['campaign_event_runs'])
                    if not relative_to:
                        relative_to = r['relative_to']
            ret = [
                {'name': 'Categories', 'data': categories},
                {'name': name, 'data': data},
                {'relative_to': relative_to}
            ]
            return json.dumps(ret)
        return ""


class Refresh:
    def GET(self):
        params = web.input(month="")
        web.header('Content-Type', 'application/json')
        if params.month:
            print params.month
            script_path = script_dir + os.sep + "parse_kannel_log.py"
            cmd = "%s %s -v -m %s" % (config['python_script'], script_path, params.month)
            print cmd
            r = os.popen(cmd)
        return json.dumps(r.read().strip())

    def POST(self):
        pass


class Users:
    @require_login
    def GET(self):
        params = web.input(page=1, ed="", d_id="")
        edit_val = params.ed

        if params.ed:
            r = db.query(
                "SELECT a.id, a.firstname, a.lastname, a.username, a.email, a.telephone, "
                "a.is_active, b.user_role as role "
                "FROM users a, user_roles b "
                "WHERE a.id = $id AND a.user_role = b.id", {'id': params.ed})
            if r and (session.role == 'Administrator' or '%s' % session.sesid == edit_val):
                u = r[0]
                firstname = u.firstname
                lastname = u.lastname
                telephone = u.telephone
                email = u.email
                username = u.username
                is_active = u.is_active
                is_super = True if u.role == 'Administrator' else False

        if params.d_id:
            if session.role == 'Administrator':
                db.query("DELETE FROM users WHERE id=$id", {'id': params.d_id})

        if session.role == 'Administrator':
            users = db.query(
                "SELECT a.id, a.firstname, a.lastname, a.username, a.email, a.telephone, b.user_role "
                "FROM users a, user_roles b WHERE a.user_role = b.id")
        else:
            users = db.query(
                "SELECT a.id, a.firstname, a.lastname, a.username, a.email, a.telephone, b.user_role "
                "FROM users a, user_roles b WHERE a.user_role = b.id "
                "AND a.id=$id", {'id': session.sesid})
        l = locals()
        del l['self']
        return render.users(**l)

    def POST(self):
        params = web.input(
            firstname="", lastname="", telephone="", username="", email="", passwd="",
            cpasswd="", is_active="", is_super="", page="1", ed="", d_id="")
        try:
            page = int(params.page)
        except:
            page = 1
        is_active = 't' if params.is_active == "on" else 'f'
        role = 'Administrator' if params.is_super == "on" else 'Basic'
        with db.transaction():
            if params.ed:
                db.query(
                    "UPDATE users SET firstname=$firstname, lastname=$lastname, "
                    "telephone=$telephone, email=$email, username=$username, "
                    "password = crypt($cpasswd, gen_salt('bf')), "
                    "is_active=$is_active, "
                    "user_role=(SELECT id FROM user_roles WHERE user_role=$role) "
                    "WHERE id = $id", {
                        'firstname': params.firstname, 'lastname': params.lastname,
                        'telephone': params.telephone, 'email': params.email,
                        'username': params.username, 'cpasswd': params.cpasswd,
                        'role': role, 'is_active': is_active, 'id': params.ed
                    }
                )
                return web.seeother("/users")
            else:
                db.query(
                    "INSERT INTO users (firstname, lastname, telephone, email, "
                    "username, password, is_active, user_role) "
                    "VALUES($firstname, $lastname, $telephone, $email, $username, "
                    "crypt($cpasswd, gen_salt('bf')), $is_active, "
                    "(SELECT id FROM user_roles WHERE user_role=$role))", {
                        'firstname': params.firstname, 'lastname': params.lastname,
                        'telephone': params.telephone, 'email': params.email,
                        'username': params.username, 'cpasswd': params.cpasswd,
                        'role': role, 'is_active': is_active, 'id': params.ed
                    }
                )
                return web.seeother("/users")
        l = locals()
        del l['self']
        return render.users(**l)


class Search:
    @require_login
    def GET(self):
        params = web.input(page=1)
        try:
            page = int(params.page)
        except:
            page = 1

        limit = SETTINGS['PAGE_LIMIT']
        start = (page - 1) * limit if page > 0 else 0
        l = locals()
        del l['self']
        return render.search(**l)

    def POST(self):
        params = web.input()
        l = locals()
        del l['self']
        return render.search(**l)


class Settings:
    @require_login
    def GET(self):
        l = locals()
        del l['self']
        return render.settings(**l)

    def POST(self):
        params = web.input()
        l = locals()
        del l['self']
        return render.settings(**l)


class Logout:
    def GET(self):
        session.kill()
        return web.seeother("/")


class SteppingStone:
    def GET(self):
        pass

    def POST(self):
        params = web.input(group="Nsambya 1")
        print params.group
        print params.phone
        data = {"phone": params.phone, "groups": ['Completed Stepping stone %s' % params.group]}
        # values = json.loads(params['values'])
        post_data = json.dumps(data)
        res = post_request(post_data)
        print res.text
        return "Done"

if __name__ == "__main__":
    app.run()

# makes sure apache wsgi sees our app
application = web.application(urls, globals()).wsgifunc()
