from urllib.parse import quote

import requests
import io
import pandas as pd
import mysql.connector
import os
from dotenv import load_dotenv


# bboxx funktio
def get_bbox(city):
    osm_url = f"https://nominatim.openstreetmap.org/search?q={quote(city)}&format=json"
    headers = {'User-Agent': 'OpenAQCityBBox'}

    response = requests.get(osm_url, headers=headers).json()

    if not response:
        return None

    # boundingbox sisältää löydetyn kaupungin rajat
    # siinä on 4 koordinaattipistettä
    osm_bbox = response[0]['boundingbox']

    # OpenStreetMapin bounding boxin koordinaatit ovat ao järjestyksessä
    # min_y, max_y, min_x, max_x
    min_lat, max_lat, min_lon, max_lon = osm_bbox

    # järjestetään uudelleen openAQ:lle sopivaan muotoon: min_x, min_y, max_x, max_y
    openaq_bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    return openaq_bbox


API_KEY = '0fa2bad4d6736109872dce1c457bffd4e743172f0c0e1dd0b2703aa302f37534'

# OpenAQ locations funktio
# tämä funktio saa parametrinaan kaupungin bounding boxin get_bbox-funktiolta
def get_openaq_locations_by_bbox(_bbox):
    response = requests.get(
        f"https://api.openaq.org/v3/locations?limit=1000&page=1&order_by=id&sort_order=asc&bbox={_bbox}",
        headers={'X-API-Key': API_KEY}
    )
    _locations = []
    # muista, että http-statuskoodi 200 on OK
    # voit myös heittää poikkeuksen,
    # jos statuskoodi on jotakin muuta kuin 200
    if response.status_code == 200:
        _locations = response.json()['results']

    return _locations

# S3‑funktio
def download_file_by_location(location_id, year, month, day):
    date_str = f"{year}{month:02d}{day:02d}"
    base_url = "https://openaq-data-archive.s3.amazonaws.com"
    key = f"records/csv.gz/locationid={location_id}/year={year}/month={month:02d}/location-{location_id}-{date_str}.csv.gz"
    full_url = f"{base_url}/{key}"

    # Use requests to get the file
    response = requests.get(full_url)

    if response.status_code == 200:
        # pandas osaa avata gzip-pakatun csv
        df = pd.read_csv(io.BytesIO(response.content), compression='gzip')
        df.to_csv(f"{location_id}-{date_str}.csv", index=False)
    else:
        print(f"Failed to fetch. Status: {response.status_code}")


load_dotenv()

# maa kaupunki sijainti
def sync_location_metadata(cursor, loc_data):
    # maa
    country_obj = loc_data.get("country", {})
    country_name = country_obj.get("name", "Unknown")
    cursor.execute("SELECT countriesID FROM countries WHERE name = %s", (country_name,))
    res = cursor.fetchone()
    if res:
        country_id = res[0]
    else:
        cursor.execute("INSERT INTO countries (name) VALUES (%s)", (country_name,))
        country_id = cursor.lastrowid

    # kaupunki
    city_name = loc_data.get('locality', 'Unknown')
    cursor.execute("SELECT citiesID FROM cities WHERE name = %s AND countriesID = %s", (city_name, country_id))
    res = cursor.fetchone()
    if res:
        city_id = res[0]
    else:
        cursor.execute("INSERT INTO cities (name, countriesID) VALUES (%s, %s)", (city_name, country_id))
        city_id = cursor.lastrowid

    # mittauspaikka
    loc_id = loc_data['id']
    cursor.execute("SELECT locationsID FROM locations WHERE locationsID = %s", (loc_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO locations (locationsID, name, citiesID) VALUES (%s, %s, %s)",
            (loc_id, loc_data['name'], city_id)
        )
    return loc_id

def insert_csv_to_db(csv_file):
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    cursor = conn.cursor()
    # lisätään datan poisto ennen uutta ajoa
    cursor.execute("DELETE FROM measurements")


    df = pd.read_csv(csv_file)

    for _, row in df.iterrows():
        # sensori
        cursor.execute(
            "SELECT sensorsID FROM sensors WHERE parameter=%s AND unit=%s",
            (row["parameter"], row["units"])
        )
        res = cursor.fetchone()
        if res:
            sensors_id = res[0]
        else:
            cursor.execute(
                "INSERT INTO sensors (parameter, unit) VALUES (%s, %s)",
                (row["parameter"], row["units"])
            )
            sensors_id = cursor.lastrowid

        # mittaus
        cursor.execute(
            """
            INSERT INTO measurements (locationsID, sensorsID, value, measured_at)
            VALUES (%s, %s, %s, %s)
            """,
            (row["location_id"], sensors_id, row["value"], row["datetime"])
        )

    conn.commit()
    cursor.close()
    conn.close()


# testikutsu
if __name__ == "__main__":
    # haetaan paikan tiedot API:sta
    city_to_search = "Helsinki"
    bbox = get_bbox(city_to_search)
    locations = get_openaq_locations_by_bbox(bbox)

    # muodostetaan yhteys ja varmistetaan ylärakenteet
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    cursor = conn.cursor()

    target_location_id = 4588
    for loc in locations:
        if loc['id'] == target_location_id:
            sync_location_metadata(cursor, loc)
            conn.commit()
            print(f"Sijainti, kaupunki ja maa lisätty tietokantaan")
            break

    cursor.close()
    conn.close()

    # viedään csv tietokantaan
    insert_csv_to_db("4588-20230101.csv")
    print("Mittausdata viety tietokantaan")
