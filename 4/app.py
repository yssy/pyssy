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

from BeautifulSoup import BeautifulSoup as BS

from flask import (Flask, g, request, abort, redirect,
                   url_for, render_template, Markup, flash)

from dict2xml import dict2xml

from decorator import decorator

app = Flask(__name__)
app.debug = True

VERSION = 4

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

import re

def fetch(url, mc=True):
    from urllib2 import urlopen
    if mc and hasattr(g,'mc'):
        if not g.mc.get(url.encode('ascii')):
            html=urlopen(url).read().decode("gbk","ignore")
            g.mc.set(url.encode('ascii'),html)
        return g.mc.get(url.encode('ascii'))
    else:
        return urlopen(url).read().decode("gbk","ignore")

def escape_html(html):
    return Markup.escape(html)

class Article:
    def __init__(self,url):
        self.url=url
        self.html=fetch(url)
        self.parse()
        
    def parse(self):
        self.board=re.findall(": (\w+?)]<hr>\\[<a href=bbsfwd",self.html)[0]
        self.content=re.findall("<pre>(.*)<\/pre>",self.html,re.M|re.S)[0]
        self.lines=self.content.split("\n")
        self.head="\n".join(self.lines[0:3])
        self.title=self.lines[1][6:]
        self.author=re.findall("<a href=\"bbsqry\\?userid=(\w+)\">\\1<\/a>",self.lines[0])[0]
        self.date=self.lines[2][9:]
        
        self.article=self.lines[3:]
        self.mainlines=set()
        self.reflines=set()
        for line in self.article:
            refline=re.findall("<font color=\"808080\">: (.*)$",line)
            if len(refline)>0:
                self.reflines.add(refline[0])
                self.mainlines.add(": "+refline[0])
            else:
                self.mainlines.add(line)
              
    def __str__(self):
        return "%s\t%s\t%s\n"%(self.author,self.date,self.title)
        
    def __repr__(self):
        return str(self)
        
    def getThread(self):
        #msg=LineMsg("Building Threads")
        self.threadPageUrl=re.findall("\[<a href='bbstfind0\?(.+?)'>",
            self.html,re.M|re.S)[0]
        return getThread(URLTHREAD+self.threadPageUrl)

def getThread(threadPageUrl):
    threadPage=fetch(threadPageUrl,mc=False)
    threadListHtml=re.findall("<table.*?>(.*?)<\/table>",threadPage,re.M|re.S)[0]
    threadList=threadListHtml.split("<tr>")[1:]
    threadUrlList=[URLARTICLE+re.findall("<a href=bbscon\?(.+?)>",sub)[0]
        for sub in threadList]
    return [Article(url) for url in threadUrlList]

def getArticleUrl(url):
    html=fetch(url)
    articleUrl=re.findall("</a>\]\[<a href='bbscon\?(.+?)'>",html,re.M|re.S)[0]
    return "bbscon?"+articleUrl

def calcRef(threads):
    for art in threads:
        max_score=0
        max_refer=0
        for other in threads:
            score=len(art.reflines.intersection(other.mainlines))
            if score>max_score:
                max_score=score
                max_refer=other
        art.refer=max_refer

def genRefTreeRoot(level,art,threads,out):
    print >>out,"""<tr><td>%s</td><td><a href="https://bbs.sjtu.edu.cn/bbsqry?userid=%s">%s</a></td>
<td>%s<a href=\"%s\" title=\"%s\">%s</a></td></tr>"""%(
        art.date,art.author,art.author,"｜"*level+"└",art.url,
        escape_html(re.sub("<.*?>","","\n".join(art.article))),
        art.title)
    for child in threads:
        if child.refer==art:
            genRefTreeRoot(level+1,child,threads,out)
    
def genRefTree(threads,out):
    for art in threads:
        if art.refer==0:
            genRefTreeRoot(0,art,threads,out)

@app.route("/tree/<path:url>")
@app.route("/tree")
def treeyssy(url):
    url=request.url
    url=url[url.rfind('/')+1:]
    from StringIO import StringIO
    from time import clock
    start=clock()
    out=StringIO()
    article=None
    threads=None
    if url.startswith(URLTHREADFIND):
        threads=getThread(URLBASE+url)
    else:
        if url.startswith(URLTHREADALL):
            url=getArticleUrl(URLBASE+url)
        article=Article(URLBASE+url)
        threads=article.getThread()
    calcRef(threads)
    genRefTree(threads,out)
    html=out.getvalue()
    out.close()
    end=clock()
    return render_template("treeyssy.html",article=article,threads=html,count=len(threads),time=(end-start))



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
    if not format in [u'json', u'xml', u'jsonp']:
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
    }
    
    result = soupdump(result)

    if format == u'xml':
        
        return dict2xml(result, roottag=roottag,
            listnames=xml_list_names, pretty=pretty)
    else:
        if pretty:
            json_result = json.dumps(result,
                ensure_ascii = False, sort_keys=True, indent=4)
        else:
            json_result = json.dumps(result, ensure_ascii = False)
        if callback != '':
            return '%s(%s);'%(callback, json_result)
        else:
            return json_result
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
        if len(re.findall(u'\[FROM: ([\w\.]*)\]',content_lines[i])) > 0:
            from_index = i
        
    from_lines = filter(lambda x:x != '',content_lines[from_index:])
    from_ip = re.findall(u'\[FROM: ([\w\.]*)\]',from_lines[0])[0]
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
    
    html = fetch(URLBASE + url, mc=False)
    soup = BS(html)
   
    body = soup.body
    result[u'board'] = body(u'input', type=u'hidden')[0][u'value']
    table = body(u'table')
    title = table[0].tr.font.b.string
    result[u'title'] = title
    result[u'chinese_title'] = re.findall('\(.*\)$', title)[0][1:-1]
    
    result[u'wiki'] = table[0].tr.a[u'href']
    
    links_bms_line = [{
        u'text':unicode(a.string), 
        u'href':a[u'href'], 
        u'action':re.findall(u'^(\w*)',a[u'href'])[0]} 
            for a in table[1](u'a')]
    
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
    
    
    bm_words = [child for child in table[3].tr.td][2:]
    result[u'bm_words'] ={ 
        u'plain': u''.join(
            filter(lambda x:x != None,(x.string for x in bm_words))),
        u'color': u''.join(unicode(x) for x in bm_words)}
    district = table[3].parent.parent(u'td', align='right')[0].string
    result[u'district'] = {u'name':district, u'char':district[0]}
    
    articles = [tr for tr in table[5]][3:] # 前面三项是\n, 标题, \n
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
    
    tables = [tab for tab in table[6:]]
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
    for tag in soup.nobr.contents:
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


if __name__ == '__main__':
    app.run()
#########################################################################
