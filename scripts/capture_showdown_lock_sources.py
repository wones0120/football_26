"""Capture immutable official pre-lock sources; no database or entry writes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin

import requests


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__();self.tables=[];self.links=[];self.text=[]
        self.table=None;self.row=None;self.cell=None;self.link=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='table':self.table=[];self.tables.append(self.table)
        elif tag=='tr' and self.table is not None:self.row=[];self.table.append(self.row)
        elif tag in ('td','th') and self.row is not None:self.cell=[]
        elif tag=='a':self.link={'url':attrs.get('href'),'text':[]}
    def handle_data(self,data):
        data=data.strip()
        if not data:return
        self.text.append(data)
        if self.cell is not None:self.cell.append(data)
        if self.link is not None:self.link['text'].append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:self.row.append(' '.join(self.cell));self.cell=None
        elif tag=='tr':self.row=None
        elif tag=='table':self.table=None
        elif tag=='a' and self.link is not None:
            self.link['text']=' '.join(self.link['text']);self.links.append(self.link);self.link=None


URLS={
    'pit_news':'https://www.steelers.com/news/',
    'pit_inactives':'https://www.steelers.com/news/archive/inactives/',
    'cle_news':'https://www.clevelandbrowns.com/news/all',
    'pit_injuries':'https://www.steelers.com/news/week-4-injury-report-browns',
    'cle_injuries':'https://www.clevelandbrowns.com/news/elgton-jenkins-out-for-week-4-against-the-steelers-injury-report',
    'pit_depth':'https://www.steelers.com/team/depth-chart/',
    'cle_depth':'https://www.clevelandbrowns.com/news/browns-announce-unofficial-depth-chart-for-week-4-vs-the-steelers',
    'pit_roster':'https://www.steelers.com/team/players-roster/',
    'cle_roster':'https://www.clevelandbrowns.com/team/players-roster/',
    'pit_transactions':'https://www.steelers.com/team/transactions/',
    'cle_transactions':'https://www.clevelandbrowns.com/team/transactions/',
    'market':'https://dknetwork.draftkings.com/moneyline-total-spread/',
    'weather':'https://api.weather.gov/points/41.506,-81.699',
    'dk_contest':'https://www.draftkings.com/draft/contest/196187074',
    'dk_salary':'https://www.draftkings.com/lineup/getavailableplayerscsv?draftGroupId=154084',
}


def capture(directory):
    output=directory/'public_sources';output.mkdir(exist_ok=False)
    def fetch(item):
        key,url=item;at=datetime.now(UTC).isoformat()
        try:
            response=requests.get(url,timeout=25,headers={'User-Agent':'FootballSlateResearch/1.0 (prospective local audit)'})
            response.raise_for_status()
            suffix='.csv' if key=='dk_salary' else '.raw'
            path=output/(key+suffix);path.write_bytes(response.content)
            meta={'url':url,'retrieved_at':at,'completed_at':datetime.now(UTC).isoformat(),'status':response.status_code,
                  'sha256':hashlib.sha256(response.content).hexdigest(),'content_type':response.headers.get('Content-Type'),'path':str(path)}
            if key=='weather':
                hourly_url=response.json()['properties']['forecastHourly'];h=requests.get(hourly_url,timeout=25);h.raise_for_status()
                (output/'weather_hourly.json').write_bytes(h.content)
                meta.update(hourly_url=hourly_url,hourly_sha256=hashlib.sha256(h.content).hexdigest())
            elif key!='dk_salary':
                parser=PageParser();parser.feed(response.text)
                (output/(key+'.parsed.json')).write_text(json.dumps({'text':' '.join(parser.text),'tables':parser.tables,'links':parser.links},indent=2))
            else:
                if not response.headers.get('Content-Type','').startswith('application/csv'):
                    raise ValueError('DraftKings response is not the official salary CSV')
            return key,meta
        except Exception as error:
            return key,{'url':url,'retrieved_at':at,'error':str(error)}
    with ThreadPoolExecutor(max_workers=6) as executor:manifest=dict(executor.map(fetch,URLS.items()))
    # Follow observed official links rather than guessing an inactive URL.
    extra={}
    for team,index,opponent in [('pit','pit_news','browns'),('cle','cle_news','steelers')]:
        page=output/(index+'.parsed.json')
        if not page.exists():continue
        for link in json.loads(page.read_text())['links']:
            href=link.get('url') or '';label=(href+' '+link['text']).lower()
            if 'inactive' in label and opponent in label:
                extra[team+'_inactives_article_'+str(len(extra))]=urljoin(URLS[index],href)
    for item in extra.items():
        key,meta=fetch(item);manifest[key]=meta
    (output/'capture_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:('captured' if 'sha256' in v else v.get('error')) for k,v in manifest.items()},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args();capture(args.directory)
