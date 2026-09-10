"""Normalize an explicitly supplied, locally licensed CSV; never downloads datasets."""
import argparse
import csv
import json
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('input',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--text-column',default='text')
parser.add_argument('--label-column',default='label')
parser.add_argument('--language',default='en')
args=parser.parse_args()
if args.input.resolve()==args.output.resolve(): parser.error('Input and output must differ')
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.input.open(encoding='utf-8-sig',newline='') as source,args.output.open('w',encoding='utf-8') as dest:
    for row in csv.DictReader(source):
        if args.text_column not in row or args.label_column not in row: raise ValueError('Configured columns are missing')
        text=' '.join(row[args.text_column].split())
        if text: dest.write(json.dumps({'text':text,'label':row[args.label_column],'language':args.language},ensure_ascii=False)+'\n')
