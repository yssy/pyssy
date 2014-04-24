#!/usr/bin/env python2

import urllib2
import json

boards = json.loads(urllib2.urlopen('http://localhost:5000/api/bbsall').read())['boards']

for b in boards:
    print 'Testing ', b['board'] , ' ',
    try:
        s = urllib2.urlopen('http://localhost:5000/api/board/'+b['board']).read()
        print 'OK ', len(s), 'bytes'
    except:
        print 'FAIL!'
