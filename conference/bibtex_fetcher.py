import requests
import csv
import logging
import argparse
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BibTeX Fetcher")

# Argument parser for input and output files
parser = argparse.ArgumentParser(description='Fetch BibTeX data for papers.')
parser.add_argument("--inputfile", default="conference.csv", metavar="*.csv", 
                    help="Input CSV file with a 'bibtex_url' column. Default: conference.csv")
parser.add_argument("--outputfile", default="conference_with_bibtex.csv", metavar="*.csv", 
                    help="Output CSV file to save results. Default: conference_with_bibtex.csv")
args = parser.parse_args()

# Function to fetch BibTeX data
def fetch_bibtex(bibtex_url):
    try:
        r = requests.get(bibtex_url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        bibtex_section = soup.find("div", id="bibtex-section")
        if bibtex_section:
            return bibtex_section.find("pre").text.strip()
        else:
            logger.warning(f"No BibTeX section found for URL: {bibtex_url}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch BibTeX data from {bibtex_url}: {e}")
        return None

# Function to read and process CSV data, and write to new CSV file
def process_csv(inputfile, outputfile):
    # Open input file for reading
    with open(inputfile, mode="r", newline="", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        rows = list(reader)

    # Open output file for writing the processed data
    with open(outputfile, mode="w", newline="", encoding="utf-8") as outfile:
        fieldnames = reader.fieldnames + ["bibtex_data"]  # Retain original columns and add 'bibtex_data' column
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        # Process each row in the CSV
        for row in rows:
            bibtex_url = row.get("bibtex_url")
            if bibtex_url:
                logger.info(f"Fetching BibTeX for URL: {bibtex_url}")
                bibtex_data = fetch_bibtex(bibtex_url)
                row["bibtex_data"] = bibtex_data if bibtex_data else "Not Available"
            else:
                row["bibtex_data"] = "No URL"
            writer.writerow(row)
            logger.info(f"Processed row for paper: {row['title']}")

# Main function to execute the processing
if __name__ == "__main__":
    logger.info(f"Processing CSV file: {args.inputfile}")
    process_csv(args.inputfile, args.outputfile)
    logger.info(f"BibTeX data fetching complete. Results saved to: {args.outputfile}")