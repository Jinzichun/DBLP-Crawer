import requests
from bs4 import BeautifulSoup
import re
import csv
import logging
import argparse
import os
import asyncio

# Argument parsing
parser = argparse.ArgumentParser(description='dblp paper crawler.')
parser.add_argument('--syear', type=int, default=2015, metavar="INT", 
                    help='Year to start the crawler. Default: 2010')
parser.add_argument("--sthreshod", type=float, default=0.4, metavar="FLOAT", 
                    help="Threshold for paper score to add to paper list. Default: 0.8")
parser.add_argument("--filename", default="conference.csv", metavar="*.csv", 
                    help="Filename to save the papers. Default: data.csv")
parser.add_argument("--strictmatch", type=bool, default=False, 
                    help="Enable conference strict match, e.g., do not match workshop. Default: False")
parser.add_argument("--conf", default=None, 
                    help="Specify conference name.")
parser.add_argument("--loglevel", choices=["debug", "info", "silent"], default="info", 
                    help="Logging level. Default: silent")
parser.add_argument("--logfilename", default="conference-dblplog.log")
args = parser.parse_args()

# Logging setup
logmap = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "silent": logging.CRITICAL
}
logger = logging.getLogger("dblp crawler log")
logger.setLevel(logmap[args.loglevel])

# File logging
ch = logging.FileHandler(args.logfilename, "w")
ch.setLevel(logmap[args.loglevel])
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

# Console logging
sh = logging.StreamHandler()
sh.setLevel(logmap[args.loglevel])
sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ch)
logger.addHandler(sh)

# Keywords and conference information
keywords = {
    "malicious": 0.2,
    "user": 0.2,
    "attack": 0.2,
    "detection": 0.2,
    "recognitio": 0.2,

}

venue_set = {
    "conference": ["ppopp", "fast", "dac", "hpca", "micro", "sc", "asplos", "isca", "usenix atc", "eurosys", "socc", "spaa", "podc", "fpga", "cgo", "date", "hot chips", "cluster", "iccd", "iccad", "icdcs", "codes+isss", "hipeac", "sigmetrics", "pact", "icpp", "ics", "vee", "ipdps", "performance", "hpdc", "itc", "lisa", "msst", "rtas", "euro-par", "sigcomm", "mobicom", "infocom", "nsdi", "sensys", "conext", "secon", "ipsn", "mobisys", "icnp", "mobihoc", "nossdav", "iwqos", "imc", "ccs", "eurocrypt", "s&p", "crypto", "usenix security", "ndss", "acsac", "asiacrypt", "esorics", "fse", "csfw", "srds", "ches", "dsn", "raid", "pkc", "tcc", "pldi", "popl", "fse", "sosp", "oopsla", "ase", "icse", "issta", "osdi", "fm", "ecoop", "etaps", "icpc", "re", "caise", "icfp", "lctes", "models", "cp", "icsoc", "saner", "icsme", "vmcai", "icws", "middleware", "sas", "esem", "issre", "hotos", "sigmod", "sigkdd", "icde", "sigir", "vldb", "cikm", "wsdm", "pods", "dasfaa", "ecml-pkdd", "iswc", "icdm", "icdt", "edbt", "cidr", "sdm", "recsys", "stoc", "soda", "cav", "focs", "lics", "socg", "esa", "ccc", "icalp", "cade/ijcar", "concur", "hscc", "sat", "cocoon", "acm mm", "siggraph", "vr", "ieee vis", "icmr", "si3d", "sca", "dcc", "eg", "eurovis", "sgp", "egsr", "icassp", "icme", "ismar", "pg", "spm", "aaai", "neurips", "acl", "cvpr", "iccv", "icml", "ijcai", "colt", "emnlp", "ecai", "eccv", "icra", "icaps", "iccbr", "coling", "kr", "uai", "aamas", "ppsn", "naacl", "cscw", "chi", "ubicomp", "uist", "group", "iui", "iss", "ecscw", "percom", "mobilehci", "icwsm", "www", "rtss", "wine", "cogsci", "bibm", "emsoft", "ismb", "recomb", "miccai"]
}

YEAR_START = args.syear
SCORE_THRESHOD = args.sthreshod

# Paper class
class Paper:
    def __init__(self, title=None, venue=None, year=None, pages=None, bibtex_url=None):
        self.title = title
        self.venue = venue
        self.year = year
        self.pages = pages
        self.authors = []
        self.score = None
        self.bibtex_url = bibtex_url

    def calScore(self):
        # Calculate paper score based on keywords
        self.score = sum(keywords[keyword] for keyword in keywords if keyword in self.title.lower())

    def __str__(self):
        # Return string representation of the paper
        return "{} {}, {} {}, BibTeX URL: {}".format(
            self.title, self.pages, self.venue, self.year, self.bibtex_url
        )

# Save paper data to CSV file, excluding score column
def savePaper2csv(paper_list, filename):
    with open(filename, "w") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "venue", "year", "pages", "authors", "bibtex_url"])  # Do not save bibtex_data column
        for paper in paper_list:
            writer.writerow([paper.title, paper.venue, paper.year, paper.pages, ", ".join(paper.authors), paper.bibtex_url])

# Extract content from HTML tag
def getContentStrings(tag):
    return "".join([getContentStrings(c) if hasattr(c, 'contents') else c.string for c in tag.contents])

# Search for conference papers
async def searchConference(conf, keywords, filename):
    dblp_url = "https://dblp.org/search/publ/inc"
    confre = re.compile(".*{}.*".format(conf), re.IGNORECASE)
    if args.strictmatch:
        confre = re.compile("(?=^((?!workshop).)*$)(?=[^@]?{}[^@]?)".format(conf), re.IGNORECASE)
    search_word = "|".join(keywords) + " streamid:conf/{}:".format(conf)

    page = 0
    year_smaller_bool = False
    paper_list = []
    max_pages = 50  # Set maximum pages

    # Open file and write header if file does not exist
    if not os.path.exists(filename):
        savePaper2csv([], filename)  # Ensure file exists with header

    # 在文件开头添加
    import time

    while not year_smaller_bool and page < max_pages:
        payload = {
            "q": search_word,
            "s": "ydvspc",
            "h": "1000",
            "b": f"{page}",
        }

        # 添加重试机制
        max_retries = 3
        for retry in range(max_retries):
            try:
                # 增加请求超时时间到60秒
                r = requests.get(dblp_url, params=payload, timeout=60)
                r.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if retry == max_retries - 1:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    return paper_list
                logger.warning(f"Request failed (attempt {retry + 1}/{max_retries}): {e}")
                # 指数退避，等待时间随重试次数增加
                wait_time = (retry + 1) * 5
                logger.info(f"Waiting {wait_time} seconds before next attempt...")
                time.sleep(wait_time)

        soup = BeautifulSoup(r.text, "html.parser")
        record_list = soup.find_all("li", class_=re.compile("year|inproceedings"))

        if not record_list:
            logger.warning("No more papers found!")
            break

        for record in record_list:
            if "year" in record["class"]:
                try:
                    year = int(record.string)
                    if year < YEAR_START:
                        year_smaller_bool = True
                        break
                except (ValueError, TypeError):
                    continue
            elif "inproceedings" in record["class"]:
                authors = record.cite.find_all(itemprop="author")
                title_tag = record.cite.find(class_="title")
                paper_title = getContentStrings(title_tag)
                paper_venue = record.cite.find(itemprop="isPartOf").string

                if not re.match(confre, paper_venue):
                    continue

                paper_pagination = record.cite.find(itemprop="pagination")
                paper_pagination = paper_pagination.string if paper_pagination else None

                pp = Paper(title=paper_title, venue=paper_venue, year=year, pages=paper_pagination)

                for author in authors:
                    pp.authors.append(author.a.string if author.a else author.string)

                pp.calScore()

                if pp.score >= SCORE_THRESHOD:
                    bibtex_tag = record.find("a", href=re.compile(".*view=bibtex.*"))
                    bibtex_url = bibtex_tag["href"] if bibtex_tag else None

                    pp.bibtex_url = bibtex_url

                    # Add paper to the list and write to the CSV
                    paper_list.append(pp)
                    with open(filename, "a") as f:
                        writer = csv.writer(f)
                        writer.writerow([pp.title, pp.venue, pp.year, pp.pages, ", ".join(pp.authors), pp.bibtex_url])

        # 在每页处理完成后添加延时，避免请求过于频繁
        time.sleep(3)
        page += 1

    logger.info(f"Found {len(paper_list)} papers for conference: {conf}")
    return paper_list

# Main function
if __name__ == "__main__":
    target_category = "conference"
    if target_category in venue_set:
        conferences = venue_set[target_category]
        for conf in conferences:
            logger.info(f"Starting search for conference: {conf}")
            # Use asyncio.run to execute the asynchronous task
            asyncio.run(searchConference(conf, keywords, args.filename))
            logger.info(f"Completed search for conference: {conf}")