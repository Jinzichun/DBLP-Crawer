import os
import requests
import csv
import logging
import argparse
from bs4 import BeautifulSoup
from tqdm import tqdm  # 引入进度条模块

# Set up logging，只输出 WARNING 及以上信息
logging.basicConfig(level=logging.ERROR)
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

# Function to加载已有数据（以防二次检索）
def load_existing_data(outputfile, key_field="title"):
    existing_data = {}
    if os.path.exists(outputfile):
        with open(outputfile, mode="r", newline="", encoding="utf-8") as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                key = row.get(key_field, "").strip()
                if key:
                    existing_data[key] = row
    return existing_data

# Function to打印统计信息（这里仅打印错误日志，可根据需要调整）
def print_statistics(inputfile, outputfile):
    total_entries = 0
    if os.path.exists(inputfile):
        with open(inputfile, mode="r", newline="", encoding="utf-8") as infile:
            reader = csv.DictReader(infile)
            total_entries = sum(1 for _ in reader)
    else:
        logger.warning(f"Input file {inputfile} does not exist.")
    
    success_entries = 0
    if os.path.exists(outputfile):
        with open(outputfile, mode="r", newline="", encoding="utf-8") as outfile:
            reader = csv.DictReader(outfile)
            for row in reader:
                bibtex_data = row.get("bibtex_data", "").strip()
                if bibtex_data and bibtex_data not in ("Not Available", "No URL"):
                    success_entries += 1
    logger.error(f"Total target entries in {inputfile}: {total_entries}")
    logger.error(f"Existing successful BibTeX entries in {outputfile}: {success_entries}")

# 边处理边写入，每处理完一条记录就保存，防止数据丢失
def process_csv(inputfile, outputfile):
    processed_data = load_existing_data(outputfile, key_field="title")
    
    # 读取输入 CSV 文件
    with open(inputfile, mode="r", newline="", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        input_rows = list(reader)
        fieldnames = reader.fieldnames.copy() if reader.fieldnames else []
        if "bibtex_data" not in fieldnames:
            fieldnames.append("bibtex_data")
    
    # 以写模式打开输出文件，边处理边写入，同时覆盖原文件
    with open(outputfile, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in tqdm(input_rows, desc="Processing papers", leave=False):
            title = row.get("title", "").strip()
            bibtex_url = row.get("bibtex_url", "").strip()
            
            # 优先使用已有数据（二次检索逻辑）
            if title in processed_data:
                existing_bibtex = processed_data[title].get("bibtex_data", "").strip()
                if existing_bibtex and existing_bibtex not in ("Not Available", "No URL"):
                    row["bibtex_data"] = existing_bibtex
                    writer.writerow(row)
                    outfile.flush()
                    continue  # 跳过后续处理
            
            # 需要获取 BibTeX 数据且存在 URL
            if bibtex_url:
                bibtex_data = fetch_bibtex(bibtex_url)
                row["bibtex_data"] = bibtex_data if bibtex_data else "Not Available"
            else:
                row["bibtex_data"] = "No URL"
            
            writer.writerow(row)
            outfile.flush()  # 每写入一条记录后刷新确保数据写入磁盘

# Main function to execute the processing
if __name__ == "__main__":
    print_statistics(args.inputfile, args.outputfile)
    process_csv(args.inputfile, args.outputfile)
