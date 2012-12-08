# -*- coding: utf-8 -*-

import sys
reload(sys)
sys.setdefaultencoding('utf-8')

import MySQLdb
from flask import (Flask, g, request, abort, redirect,
                   url_for, render_template, Markup, flash)

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



#########################################################################
