import argparse
import bs4
import mwapi
import os
import requests
import shutil
import sys


def get_filename(title):
    return '%s.html' % title.replace(' ', '_').replace(':', '_').replace('/', '_')


def get_pages(session):
    cont = None
    while True:
        res = session.get(action='query', list='allpages', format='json', apcontinue=cont)
        for page in res['query']['allpages']:
            yield page['title']
        cont = res.get('continue', {}).get('apcontinue')
        if not cont:
            break


def fetch_image(filename, url, skip_cert_verification):
    try:
        response = requests.get(url, verify=(not skip_cert_verification))
    except requests.exceptions.SSLError:
        print('SSL error. Pass --skip_cert_verification to ignore.')
        raise
    with open(filename, mode='wb') as f:
        f.write(response.content)


def fetch_page(session, title, out_dir, head, skip_cert_verification):
    page = session.get(action='parse', page=title, prop='text|images', format='json')['parse']
    wiki_html = page['text']['*']
    image_titles = ['File:%s' % i for i in page['images']]
    if image_titles:
        imageinfo = session.get(action='query', prop='imageinfo', iiprop='url', titles='|'.join(image_titles), format='json')
        for img in imageinfo['query']['pages'].values():
            assert img['title'].startswith('File:')
            filename = os.path.join(out_dir, 'img', img['title'][len('File:'):])
            url = img['imageinfo'][0]['url']
            fetch_image(filename, url, skip_cert_verification)
    soup = bs4.BeautifulSoup(wiki_html, features='html.parser')
    for a in soup.find_all('a'):
        if a.attrs['href'].startswith('/wiki'): # TODO: maybe this should be customized (wikiprefix)
            a.attrs['href'] = get_filename(a.attrs['href'][len('/wiki') + 1:])
        if 'image' in a.attrs.get('class', []):
            child_soup = bs4.BeautifulSoup(a.decode_contents(), features='html.parser')
            for img in child_soup.find_all('img'):
                filename = img.attrs['alt']
                del img.attrs['alt']
                img.attrs['src'] = 'img/' + filename
            a.replaceWith(child_soup)
    for span in soup.find_all('span'):
        if 'mw-editsection' in span.attrs.get('class', []):
            span.replaceWith('')
    html = '<html>%s<body>%s</body></html>' % (head or '', soup)
    with open(os.path.join(out_dir, get_filename(title)), mode='w') as f:
        f.write(html)


def main(wiki_host, api_path, out_dir, head, skip_cert_verification=False):
    session = mwapi.Session(host=wiki_host, api_path=api_path, user_agent='mwdumper')
    for title in get_pages(session):
        fetch_page(session, title, out_dir, head, skip_cert_verification)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '--wiki_host', required=True, help='The MediaWiki host to crawl, including the protocol (http://, https://)')
    parser.add_argument('-p', '--api_path', default='/api.php', help='The api path (for example "/api.php")')
    parser.add_argument('-o', '--out_dir', default='out/')
    parser.add_argument('-d', '--head', help='File whose contents to include as the output HTML''s <head>...</head>')
    parser.add_argument('-s', '--skip_cert_verification', default=False, action='store_true', help='Do not verify https certificates.')
    parser.add_argument('-f', '--force', default=False, action='store_true', help='Overwrite out_dir if it already exists.')
    args = parser.parse_args()

    if os.path.exists(args.out_dir) and args.force:
        shutil.rmtree(args.out_dir)

    if os.path.exists(args.out_dir):
        print('out_dir already exists. Use --force to remove it.')
        sys.exit(1)

    os.mkdir(args.out_dir)
    os.mkdir(os.path.join(args.out_dir, 'img'))

    if args.head:
        with open(args.head) as f:
            head = f.read()
    else:
        head = None

    main(args.wiki_host, args.api_path, args.out_dir, head, args.skip_cert_verification)
