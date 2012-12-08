# -*- coding: utf-8 -*-

import sys
reload(sys)
sys.setdefaultencoding('utf-8')

import json, re
from datetime import datetime


from BeautifulSoup import BeautifulSoup as BS
import MySQLdb
from flask import (Flask, g, request, abort, redirect,
                   url_for, render_template, Markup, flash)
from jinja2 import escape

app = Flask(__name__)
app.debug = True

import sae.core,sae
import pylibmc

@app.before_request
def before_request():
    appinfo = sae.core.Application()
    g.mc = pylibmc.Client()
    

@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'): g.db.close()



@app.route('/')
def hello():
    html= """
        <p>欢迎使用pyssy工具。</p>
        <p>请将水源的网址中http://bbs.sjtu.edu.cn/ 替换为 http://pyssy.sinasae.com/&lt;service&gt;/ </p>
        <p>目前支持的service有： tree —— 树状主题列表</p>
        <p>%s</p>
        <p>%s</p>
        """ %( str(dir(sae)) , str(dir(sae.conf)))
    return render_template('template.html',body=html)


##########################################################################
URLBASE="http://bbs.sjtu.edu.cn/"
URLTHREAD=URLBASE+"bbstfind0?"
URLARTICLE=URLBASE+"bbscon?"
URLTHREADALL="bbstcon"
URLTHREADFIND="bbstfind"

import re

def fetch(url,mc=True):
    from urllib2 import urlopen
    if mc:
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
    if isinstance(var,list):
        return [soupdump(x) for x in var]
    if isinstance(var,dict):
        return dict((x,soupdump(var[x])) for x in var)
    if isinstance(var, int):
        return var
    if hasattr(var,'string'):
        return unicode(var.string)
    else:
        return unicode(var)

@app.route('/api/article/<path:url>')
@app.route('/api/article')
def article(url):
    # Underscope is not in resulted json
    _url = request.url
    _url = _url[_url.rfind(u'/') + 1:]
    _html = fetch(URLBASE + _url)
    _soup = BS(_html)
    
    page_title = _soup.title
    _body = _soup.body.center
    body_title = _body.contents[1]
    _board_str = _body.contents[2] # "[讨论区: BOARD]"
    board = _board_str[_board_str.rfind(':') + 2 : -1 ]
    
    _links_index = [5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25]
    _links = [_body.contents[_x] for _x in _links_index]
    links = []
    for _link in _links:
        links.append({
            u'url' : _link[u'href'],
            u'string' : _link.string,
            u'action' : re.findall(u'^(\w*)',_link[u'href'])[0],
            })
    
    _content = _body.table.tr.pre #<pre>content</pre>
    author = _content.a
    
    _content_raw = unicode(_content)[5:-6]
    content_lines = _content_raw.split(u'\n')
    _datetime_str = unicode(content_lines[2])[11:30]
    
    _datetime_list = [ int(_datetime_str[0:4]),
                        int(_datetime_str[5:7]),
                        int(_datetime_str[8:10]),
                        int(_datetime_str[11:13]),
                        int(_datetime_str[14:16]),
                        int(_datetime_str[17:19]),
                        ]
    _datetime = datetime(*_datetime_list)
    
    _from_index = -1
    for i in range(len(content_lines)-1,-1,-1):
        if len(re.findall(u'\[FROM: ([\w\.]*)\]',content_lines[i])) > 0:
            _from_index = i
        
    _from_lines = filter(lambda x:x != '',content_lines[_from_index:])
    #return repr(_from_lines)
    _from_ip = re.findall(u'\[FROM: ([\w\.]*)\]',_from_lines[0])[0]
    _edit_times = len(_from_lines) - 1 # 来自那行,和最后</font>的一行
    
    _qmd_index = -1
    for i in range(len(content_lines)-1,-1,-1):
        if content_lines[i] == u'--':
            _qmd_index = i
            break
    if _qmd_index != -1:
        _qmd_lines = content_lines[_qmd_index+1:_from_index]        
    else:
        _qmd_lines = []
    
    _response_index = -1
    for i in range(_qmd_index, -1, -1):
        if len(re.findall(u'^【 在.*的大作中提到: 】$',content_lines[i])) > 0:
            _response_index = i
            break
    if _response_index == -1:
        _response_index = _qmd_index
    if _response_index != -1:
        _response_lines = content_lines[_response_index:_qmd_index - 1] 
        for i in range(1,len(_response_lines)):
            if len(re.findall(u'<font color="808080">: (.*)$',_response_lines[i])) > 0:
                _response_lines[i] = re.findall(u'<font color="808080">: (.*)$',_response_lines[i])[0]
    else:
        _response_lines = []
        
    _text_lines = content_lines[4:_response_index]
    
    content = {
        u'author': _content.a ,
        u'board' : content_lines[0][content_lines[0].rfind(' ') + 1:] ,
        u'title' : content_lines[1][6:] ,
        u'datetime_str' : _datetime_str ,
        u'datetime_list' : _datetime_list ,
        u'datetime' : _datetime.ctime() ,
        u'qmd_lines' : _qmd_lines ,
        u'from_lines' : _from_lines ,
        u'from_ip' : _from_ip ,
        u'response_lines' : _response_lines,
        u'text_lines' : _text_lines,
        u'edit_times' : _edit_times, 
    }
    
    del i
    del url
    ls = locals()
    result = {}
    for key in ls:
        if key.startswith('_'): continue
        result[key] = soupdump(ls[key])
        
    return json.dumps( result, ensure_ascii = False, sort_keys=True, indent=4)
    #return content.text
#########################################################################
