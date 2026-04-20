from flask import Flask, jsonify, request
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

# 1 päivän mittaukset location
@app.route("/api/measurements", methods=["GET"])
def get_measurements():
    location_id = request.args.get("location_id")
    day = request.args.get("day")  # YYYY-MM-DD

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT measured_at, value
        FROM measurements
        WHERE locationsID = %s
        AND DATE(measured_at) = %s
    """, (location_id, day))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(rows)

# mittausten lkm location
@app.route("/api/measurements/count", methods=["GET"])
def get_count():
    location_id = request.args.get("location_id")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM measurements
        WHERE locationsID = %s
    """, (location_id,))

    count = cur.fetchone()[0]
    cur.close()
    conn.close()

    return jsonify({"count": count})

# päivän keskiarvo location + sensor
@app.route("/api/measurements/avg", methods=["GET"])
def get_avg():
    location_id = request.args.get("location_id")
    sensor_id = request.args.get("sensor_id")
    day = request.args.get("day")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT AVG(value)
        FROM measurements
        WHERE locationsID = %s
        AND sensorsID = %s
        AND DATE(measured_at) = %s
    """, (location_id, sensor_id, day))

    avg = cur.fetchone()[0]
    cur.close()
    conn.close()

    return jsonify({"average": avg})

if __name__ == "__main__":
    app.run(debug=True)
