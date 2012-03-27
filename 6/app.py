# -*- coding: utf-8 -*-
try:
    # try to load sae to test are we on sina app engine
    import sae

    # reload sys to use utf-8 as default encoding
    import sys
    reload(sys)
    
    sys.setdefaultencoding('utf-8')
    import pylibmc
    import sae
    import sae.core
    
    PYSSY_SAE = True
except:
    PYSSY_SAE = False


import json, re
from datetime import datetime
import time
from urllib2 import urlopen

from BeautifulSoup import BeautifulSoup as BS

from flask import (Flask, g, request, abort, redirect,
                   url_for, render_template, Markup, flash, Response)

from dict2xml import dict2xml

from decorator import decorator

app = Flask(__name__)
app.debug = True

VERSION = 5

app.config[u'VERSION'] = VERSION
@app.before_request
def before_request():
    if PYSSY_SAE:
        appinfo = sae.core.Application()
        g.mc = pylibmc.Client()
    

@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'): g.db.close()



@app.route('/')
def hello():
    html= u"""
        <p>欢迎使用pyssy工具。</p>
        <p>请将水源的网址中http://bbs.sjtu.edu.cn/ 替换为 http://pyssy.sinasae.com/&lt;service&gt;/ </p>
        <p>目前支持的service有： tree —— 树状主题列表</p>
        """ 
    return render_template('template.html',body=html)


##########################################################################
URLBASE="http://bbs.sjtu.edu.cn/"
URLTHREAD=URLBASE+"bbstfind0?"
URLARTICLE=URLBASE+"bbscon?"
URLTHREADALL="bbstcon"
URLTHREADFIND="bbstfind"


# default timeout is 10 seconds
def fetch(url, timeout = 10):
    if timeout > 0 and hasattr(g,'mc'):
        result = g.mc.get(url.encode('ascii'))
        if result and result is dict:
            expired = (datetime.now() - result['time']).total_seconds() > timeout
            if not expired:
                return result['html']
        html = urlopen(url).read().decode("gbk","ignore")
        g.mc.set(url.encode('ascii'), {'html':html,'time':datetime.now()})
        return html
    else:
        return urlopen(url).read().decode("gbk","ignore")

def soupdump(var):
    if isinstance(var,tuple):
        return [soupdump(x) for x in var]
    if isinstance(var,list):
        return [soupdump(x) for x in var]
    if isinstance(var,dict):
        return dict((x,soupdump(var[x])) for x in var)
    if isinstance(var, int):
        return var
    if isinstance(var, float):
        return var
    if hasattr(var,'string'):
        return unicode(var.string)
    else:
        return unicode(var)

@decorator
def api(func, *args, **kwargs):
    format, pretty, callback = kwargs['format'], kwargs['pretty'], kwargs['callback']
    del kwargs['format'], kwargs['pretty'], kwargs['callback']
    if not format in [u'json', u'xml', u'jsonp', u'raw']:
        return u'Format "%s" not supported! Use "json" or "xml".'%format
    if format == u'json' and callback != u'':
        format = u'jsonp'
    
    result, xml_list_names, roottag = func(*args, **kwargs)
    
    result[u'api'] = {
        u'args'         : args,
        u'kargs'        : kwargs, 
        u'request_url'  : request.url,
        u'format'       : format,
        u'pretty'       : pretty,
        u'callback'     : callback,
        u'version'      : app.config[u'VERSION'],
        u'values'       : request.values,
        u'name'         : roottag,
    }
    
    result = soupdump(result)
    xml_list_names['args'] = u'arg'
    
    if format == u'raw':
        return result
    elif format == u'xml':
        return Response(dict2xml(result, roottag=roottag,
            listnames=xml_list_names, pretty=pretty), content_type=u'text/xml')
    else:
        if pretty:
            json_result = json.dumps(result,
                ensure_ascii = False, sort_keys=True, indent=4)
        else:
            json_result = json.dumps(result, ensure_ascii = False)
        if callback != '':
            return Response('%s(%s);'%(callback, json_result), content_type=u'application/javascript')
        else:
            return Response(json_result, content_type=u'application/json')
@app.route(u'/api/article/<board>/<file_>', methods=[u'GET', u'POST'])
def rest_article(board, file_):
    ext = file_[file_.rindex(u'.')+1:]
    if ext in [u'json', u'xml', u'jsonp']:
        format = ext
        file_ = file_[:file_.rindex(u'.')]
    else:
        format = 'json'
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    if 'callback' in request.values:
        callback = request.values['callback']
        if format == 'json':
            format = 'jsonp'
    else:
        callback = '' 
    url = u'bbscon?board=%s&file=%s'%(board, file_)
    return article(url, format=format, pretty=pretty, callback=callback)
    
@app.route(u'/api/article', methods=[u'GET', u'POST'])
def api_article():
    if 'url' in request.values:
        url = request.values[u'url']
    else:
        file_ = request.values[u'file']
        board = request.values[u'board']
        url = u'bbscon?board=%s&file=%s'%(board, file_)
    if 'format' in request.values:
        format = request.values['format']
    else:
        format = 'json'
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    if 'callback' in request.values:
        callback = request.values['callback']
    else:
        callback = '' 
    url = url[url.rfind(u'/') + 1:]
    return article(url, format=format, pretty=pretty, callback=callback)

@app.route('/article/<path:url>', methods=['GET', 'POST'])
@app.route('/article', methods=['GET', 'POST'])
def url_article(url):
    url = request.url
    if 'format' in request.values:
        format = request.values['format']
    else:
        format = 'json'
    if 'callback' in request.values:
        callback = request.values['callback']
    else:
        callback = '' 
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    url = url[url.rfind(u'/') + 1:]
    return article(url, format=format, pretty=pretty, callback=callback)

@api
def article(url, *args, **kwargs):
    result = {}
    result[u'url'] = url
    
    html = fetch(URLBASE + url)
    soup = BS(html)
    
    result[u'page_title'] = soup.title
    body = soup.body.center
    result[u'body_title'] = body.contents[1]
    board_str = body.contents[2] # "[讨论区: BOARD]"
    result[u'board'] = board_str[board_str.rfind(':') + 2 : -1 ]
    
    link_index = [5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25]
    links = [body.contents[x] for x in link_index]
    result[u'links'] = []
    for link in links:
        result[u'links'].append({
            u'url' : link[u'href'],
            u'string' : link.string,
            u'action' : re.findall(u'^(\w*)',link[u'href'])[0],
            })
            
    re_link = unicode(filter(lambda x: x[u'action']==u'bbspst', result[u'links'])[0]['url'])
    result['reid'] = int(re.findall(u'(\w*)$',re_link)[0])
    
    content = body.table.tr.pre #<pre>content</pre>
    content_raw = unicode(content)[5:-6]
    content_lines = content_raw.split(u'\n')
    result[u'content_lines'] = content_lines
    datetime_str = unicode(content_lines[2])[11:30]
    
    datetime_tuple = [ int(datetime_str[0:4]),
                        int(datetime_str[5:7]),
                        int(datetime_str[8:10]),
                        int(datetime_str[11:13]),
                        int(datetime_str[14:16]),
                        int(datetime_str[17:19]),]
    datetime_ = datetime(*datetime_tuple)
    
    from_index = -1
    for i in range(len(content_lines)-1, -1, -1):
        if len(re.findall(u'\[FROM: ([\w\.:]*)\]',content_lines[i])) > 0:
            from_index = i
        
    from_lines = filter(lambda x:x != '',content_lines[from_index:])
    if len(from_lines)>0:
        from_ip = re.findall(u'\[FROM: ([\w\.:]*)\]',from_lines[0])[0]
    else:
        from_ip = ''
    edit_times = len(from_lines) - 1 # 来自那行,和最后</font>的一行
    
    qmd_index = -1
    for i in range(len(content_lines)-1,-1,-1):
        if content_lines[i] == u'--':
            qmd_index = i
            break
    if qmd_index != -1:
        qmd_lines = content_lines[qmd_index + 1 : from_index]        
    else:
        qmd_lines = []
    
    reply_index = -1
    for i in range(qmd_index, -1, -1):
        if len(re.findall(u'^【 在.*的大作中提到: 】$',content_lines[i])) > 0:
            reply_index = i
            break
    if reply_index == -1:
        reply_index = qmd_index
    if reply_index != -1:
        reply_lines = content_lines[reply_index : qmd_index - 1] 
        for i in range(1,len(reply_lines)):
            if len(re.findall(u'<font color="808080">: (.*)$',reply_lines[i])) > 0:
                reply_lines[i] = re.findall(
                    u'<font color="808080">: (.*)$',reply_lines[i])[0]
    else:
        reply_lines = []
        
    text_lines = content_lines[4:reply_index]
    

    
    result[u'content'] = {
        u'author': content.a ,
        u'author_link': content.a[u'href'] ,
        u'board' : content_lines[0][content_lines[0].rfind(' ') + 1:] ,
        u'title' : content_lines[1][6:] ,
        u'datetime_str' : datetime_str ,
        u'datetime_tuple' : datetime_tuple ,
        u'datetime_epoch' : repr(time.mktime(datetime_.timetuple())),
        u'datetime_ctime' : datetime_.ctime() ,
        u'qmd_lines' : qmd_lines ,
        u'from_lines' : from_lines ,
        u'from_ip' : from_ip ,
        u'reply_lines' : reply_lines,
        u'text_lines' : text_lines,
        u'edit_times' : edit_times, 
    }
    
    xml_list_names= {
        u'qmd_lines':       u'line', 
        u'content_lines':   u'line',
        u'text_lines':      u'line',
        u'reply_lines':     u'line', 
        u'from_lines':      u'line',
        u'datetime_tuple':   u'int',
        u'links':           u'link',
        u'args':            u'arg',
    }

    return (result, xml_list_names, 'article')
@app.route(u'/api/board', methods=[u'GET', u'POST'])
def api_board():
    if 'url' in request.values:
        url = request.values[u'url']
    else:
        board_ = request.values[u'board']
        if 'page' in request.values:
            page_str = request.values[u'page']
            page_re = re.findall('[0-9]+',page_str)
            if len(page_re) > 0:
                page = int(page_re[0])
                url = u'bbsdoc?board=%s&page=%d'%(board_, page)
            else:
                page = 'latest'
                url = u'bbsdoc?board=%s'%(board_)
        else:
            page = 'latest'
            url = u'bbsdoc?board=%s'%(board_)
    if 'format' in request.values:
        format = request.values['format']
    else:
        format = 'json'
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    if 'callback' in request.values:
        callback = request.values['callback']
    else:
        callback = '' 
    return board(url, format=format, pretty=pretty, callback=callback)

@app.route(u'/board/<path:url>', methods=[u'GET', u'POST'])
@app.route(u'/board', methods=[u'GET', u'POST'])
def url_board(url):
    url = request.url
    if 'format' in request.values:
        format = request.values['format']
    else:
        format = 'json'
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    if 'callback' in request.values:
        callback = request.values['callback']
    else:
        callback = '' 
    url = url[url.rfind(u'/') + 1:]
    return board(url, format=format, pretty=pretty, callback=callback)

@app.route('/api/board/<b>', methods=['GET', 'POST'])
def rest_board(b):
    if u'.' in b:
        ext = b[b.rindex(u'.')+1:]
        if ext in [u'json', u'xml', u'jsonp']:
            format = ext
            b = b[:b.rindex(u'.')]
        else:
            format = 'json'
    else:
        format = 'json'
    board_ = b
    if 'page' in request.values:
        page_str = request.values[u'page']
        page_re = re.findall('[0-9]+',page_str)
        if len(page_re) > 0:
            page = int(page_re[0])
            url = u'bbsdoc?board=%s&page=%d'%(board_, page)
        else:
            page = 'latest'
            url = u'bbsdoc?board=%s'%(board_)
    else:
        page = 'latest'
        url = u'bbsdoc?board=%s'%(board_)
    if 'format' in request.values:
        format = request.values['format']
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    if 'callback' in request.values:
        callback = request.values['callback']
    else:
        callback = '' 
    return board(url, format=format, pretty=pretty, callback=callback)
@api
def board(url, *args, **kwargs):
    result = {}
    
    html = fetch(URLBASE + url, timeout = 1)
    soup = BS(html)
    result[u'board'] = soup.body(u'input', type=u'hidden')[0][u'value']
    title = soup.body.table.tr.font.b.string
    result[u'title'] = title
    result[u'chinese_title'] = re.findall('\(.*\)$', title)[0][1:-1]
    
    result[u'wiki'] = soup.body.table.tr.a[u'href']
    
    nobr = soup.nobr
    
    
    links_bms_line = [{
        u'text':unicode(a.string), 
        u'href':a[u'href'], 
        u'action':re.findall(u'^(\w*)',a[u'href'])[0]} 
            for a in nobr.table(u'a')]
    
    result[u'bms'] = [bm[u'text'] for bm in 
        filter( lambda x:x[u'href'].startswith(u'bbsqry?userid='), 
            links_bms_line)]
    
    result[u'up_links'] = filter( 
        lambda x: not x[u'href'].startswith(u'bbsqry?userid='),
        links_bms_line)
        
    result[u'has_next_page'] = len(
        filter(lambda x: x[u'text']== u'下一页', result[u'up_links'])
        ) > 0
    
    result[u'has_prev_page'] = len(
        filter(lambda x: x[u'text']== u'上一页', result[u'up_links'])
        ) > 0
    
    if result[u'has_prev_page']:
        prev_page = unicode(filter(lambda x: x[u'text']== u'上一页', result[u'up_links'])[0]['href'])
        result[u'page'] = int(re.findall(u'[0-9]+',prev_page)[0]) + 1
    else:
        result[u'page'] = 0
    
    table2 = nobr.contents[3].tr.contents

    if table2[0].string == None:
        bm_words = [child for child in table2[0].table.tr.td][2:]
        result[u'bm_words'] ={ 
            u'plain': u''.join(
                filter(lambda x:x != None,(x.string for x in bm_words))),
            u'color': u''.join(unicode(x) for x in bm_words)}
    else:
        result[u'bm_words'] ={u'plain': u'',u'color': u''}

    district = table2[1].string
    result[u'district'] = {u'name':district, u'char':district[0]}
    #return ({u'r':[unicode(x) for x in nobr.contents]},{},u'debug')
    
    articles = [tr for tr in nobr.contents[6].table][3:] # 前面三项是\n, 标题, \n
    result[u'articles'] = []
    result[u'fixed_articles'] = []
    for art in articles:
        art_list = [item for item in art]
        words_str = [string for string in art_list[4].contents][2].string
        if words_str[-1] == 'K':
            words = int(float(words_str[:-1])*1000)
        else:
            words = int(words_str[:-1])
        mark = art_list[1].string
        mark = mark if mark != None else u''
        link = unicode(art_list[4].a[u'href'])
        file_ = re.findall(u'file.(.+?)(\.html){0,1}$', link)[0][0]
        datetime_str = art_list[3].string
        current_year = str(datetime.now().year)+datetime_str
        datetime_ = datetime.strptime(current_year,'%Y%b %d %H:%M')
        article = {
            u'id': art_list[0],
            u'mark': mark,
            u'author': art_list[2].a,
            u'datetime_str': datetime_str,
            u'datetime_ctime': datetime_.ctime(),
            u'datetime_tuple': tuple(datetime_.timetuple()[:6]),
            u'datetime_epoch': repr(time.mktime(datetime_.timetuple())),
            u'title': art_list[4].a,
            u'link': link,
            u'file': file_,
            u'words_str': words_str,
            u'words' : words
        }
        
        font = article[u'id'](u'font') 
        if len(font) == 0:
            article[u'id'] = int(article[u'id'].string)
            result[u'articles'].append(article)
        else:
            article[u'type'] = font[0]
            del article[u'id']
            result[u'fixed_articles'].append(article)
    
    tables = [tab for tab in nobr.contents[6]('table')[1:]]
    result[u'other_tables'] = []

    for tab in tables:
        name = unicode(tab.contents[1].td.string)
        tds = filter(lambda td: td.find('a')!= None, tab(u'td'))
        if name == u'板主推荐':
            links = [{u'href': td.a[u'href'],
                      u'text': td.a.string} for td in tds]
            result[u'bm_recommends'] = links
        elif name == u'友情链接':
            links = [{u'href':    td.a[u'href'],
                      u'board':   td.a.contents[0], 
                      u'chinese': td.contents[1]} for td in tds]
            result[u'friend_links'] = links
        else:
            result[u'other_tables'].append({u'name':name,u'links':links})
    
    down_links = [ ]
    after_hr = False
    for tag in nobr.contents:
        if not hasattr(tag, u'name'): continue
        if tag.name == u'hr':
            after_hr = True 
        if after_hr and tag.name == u'a':
            down_links.append(tag)
        
    result['down_links'] = [{u'href': tag[u'href'],
                             u'action': re.findall(u'^(\w*)', tag[u'href'])[0],
                             u'text': u''.join(unicode(child) for child in tag.contents),
                            } for tag in down_links]
    
    xml_map = { u'bms':             u'bm',
                u'up_links':        u'link',
                u'args':            u'arg',
                u'articles':        u'article',
                u'fixed_articles':  u'article',
                u'down_links':      u'link',
                u'friend_links':    u'link',
                u'datetime_tuple':  u'int',
              }
    return (result, xml_map, u'board')


@app.route(u'/api/thread/<board>/<reid>', methods=[u'GET', u'POST'])
def rest_thread(board, reid):
    ext = reid[reid.rindex(u'.')+1:]
    if ext in [u'json', u'xml', u'jsonp']:
        format = ext
        reid = reid[:reid.rindex(u'.')]
    else:
        format = 'json'
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    if 'callback' in request.values:
        callback = request.values['callback']
        if format == 'json':
            format = 'jsonp'
    else:
        callback = '' 
    url = u'bbstfind0?board=%s&reid=%s'%(board, reid)
    return thread(url, format=format, pretty=pretty, callback=callback)
    
@app.route('/thread/<path:url>', methods=['GET', 'POST'])
@app.route('/thread', methods=['GET', 'POST'])
def url_thread(url):
    url = request.url
    if 'format' in request.values:
        format = request.values['format']
    else:
        format = 'json'
    if 'callback' in request.values:
        callback = request.values['callback']
    else:
        callback = '' 
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    url = url[url.rfind(u'/') + 1:]
    return thread(url, format=format, pretty=pretty, callback=callback)

@app.route(u'/api/thread', methods=[u'GET', u'POST'])
def api_thread():
    if 'url' in request.values:
        url = request.values[u'url']
    else:
        reid = request.values[u'reid']
        board = request.values[u'board']
        url = u'bbstfind0?board=%s&reid=%s'%(board, reid)
    if 'format' in request.values:
        format = request.values['format']
    else:
        format = 'json'
    if 'pretty' in request.values:
        pretty = int(request.values['pretty']) == 1
    else:
        pretty = False
    if 'callback' in request.values:
        callback = request.values['callback']
    else:
        callback = '' 
    url = url[url.rfind(u'/') + 1:]
    return thread(url, format=format, pretty=pretty, callback=callback)

@api
def thread(url, *args, **kwargs):
    result = {}
    html = fetch(URLBASE + url, timeout = 1)
    soup = BS(html)
    center = soup.center.contents
    
    result[u'page_title'] = center[0]
    headline = center[1]
    result[u'board'] = re.findall(u'\[讨论区: (.+?)\]', headline)[0]
    result[u'topic'] = re.findall(u" \[主题 '(.+?)'\]", headline)[0]
    
    trs = soup.table(u'tr')[1:]
    result['articles'] = []
    for tr in trs:
        cont = tr.contents
        datetime_str = cont[2].string
        current_year = unicode(datetime.now().year)+datetime_str
        datetime_ = datetime.strptime(current_year, u'%Y%b %d')
        link = cont[3].a[u'href']
        board = re.findall(u'board=(.+?)&', link)[0]
        file_ = re.findall(u'file=(.+)$', link)[0]
        art = {
            u'id': int(cont[0].string),
            u'user': cont[1].a ,
            u'user_link': cont[1].a[u'href'], 
            u'datetime_str': datetime_str,
            u'datetime_ctime': datetime_.ctime(),
            u'datetime_tuple': tuple(datetime_.timetuple()[:6]),
            u'datetime_epoch': repr(time.mktime(datetime_.timetuple())),
            u'title': cont[3].a,
            u'link': link,
            u'board': board,
            u'file': file_,
        }
        result['articles'].append(art)
    result[u'count'] = int(re.findall(u'共找到 ([0-9]+) 篇',center[6])[0])
    result[u'board_link'] = center[7][u'href']
    result[u'bbstcon_link'] = center[9][u'href']
    

    return (result,{'datetime_tuple':'int','articles':'article'},u'thread')
def treehtml(art):
    replies = []
    art[u'replies'].sort(key = lambda x:float(x[u'content'][u'datetime_epoch']))
    for reply in art[u'replies']:
        replies.append(treehtml(reply))
    return render_template(u'treeart.html',
        article=art, replies=replies, 
        content_lines = u'\n'.join(art[u'content_lines']),
        baseurl = URLBASE)

def calcscore(art, other, maxp):
    from difflib import get_close_matches
    score = 0
    for line in art[u'reply_lines']:
        for otherline in (other[u'text_lines']):
            l1 = len(line)
            l2 = len(otherline)
            l = l1 if l1 < l2 else l2
            if len(set(line).intersection(otherline)) > l/2:
                score += 1
    return score

@app.route(u"/tree/<path:url>")
@app.route(u"/tree")
def tree(url):
    url=request.url
    url=url[url.rfind(u'/')+1:]
    from time import clock
    start=clock()

    thread_json = thread(url, format=u'raw', callback=u'', pretty=False)
    threads = []
    index = 0
    for art in thread_json[u'articles']:
        art_json = article(art[u'link'], format=u'raw', callback=u'', pretty=False)
        art_json['text_lines'] = []
        for line in art_json['content']['text_lines']:
            while len(line)>80:
                art_json['text_lines'].append(line[:80])
                line = line[80:]
            if len(line.strip()) > 0:
                art_json['text_lines'].append(line)
                
        art_json['reply_lines'] = []
        for line in art_json['content']['reply_lines']:
            while len(line)>80:
                art_json['reply_lines'].append(line[:80])
                line = line[80:]
            art_json['reply_lines'].append(line)
        
        art_json[u'replies'] = []
        art_json[u'index'] = index
        index += 1
        threads.append(art_json)
        
    maxp = len(threads)
    
    for art in threads:
        max_score = 0
        max_refer = None
        for other in threads:
            if other['index'] == art['index']:
                continue
            score = calcscore(art, other, maxp)
            if score > max_score:
                max_score = score
                max_refer = other
        art[u'refer'] = max_refer
        art[u'score'] = max_score
        if max_refer != None:
            max_refer[u'replies'].append(art)
    
    for art in threads[1:]:
        if art[u'refer'] == None:
            art[u'refer'] = threads[0]
            threads[0][u'replies'].append(art)
    
    end=clock()
    
    #ans = []
    #for art in threads[1:]:
    #    ans.append('%s -> %s'%(art[u'index'],art[u'refer'][u'index']))
    #return '<br/>'.join(ans)
    return render_template('treeyssy.html',treehtml = treehtml(threads[0]),thread = thread_json, time = end - start)



if __name__ == '__main__':
    app.run()
#########################################################################
