import cv2
import easyocr
import re
import gradio as gr
import psycopg2
from datetime import datetime

def get_db_connection():
    connection = psycopg2.connect(
        user="postgres",
        password="1234!",
        host="localhost",
        port="5432",  # default port
        database="ocr_data"
    )
    return connection


def preprocess_image(image_path):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def extract_text_from_image(image_path):
    img = cv2.imread(image_path)
    reader = easyocr.Reader(['en'])
    result = reader.readtext(img, detail=0)
    return '\n'.join(result)


def extract_pan_details(text):
    pan_pattern = r"[A-Z]{5}[0-9]{4}[A-Z]"
    dob_pattern = r"\d{2}/\d{2}/\d{4}"

    lines = [line.strip() for line in text.split('\n') if line.strip()]

    start_index = 0
    for i, line in enumerate(lines):
        if 'income tax department' in line.lower() or 'govt. of india' in line.lower():
            start_index = i
            break

    lines = lines[start_index:]  # Skip anything before English text

    filtered_lines = [line for line in lines if 'govt. of india' not in line.lower() and 'income tax department' not in line.lower()]

    cardholder_name = 'Not Found'
    father_name = 'Not Found'

    if len(filtered_lines) >= 2:
        cardholder_name = filtered_lines[0]
        father_name = filtered_lines[1]

    pan_match = re.search(pan_pattern, text)
    dob_match = re.search(dob_pattern, text)

    return {
        'Type': 'PAN',
        'PAN No.': pan_match.group() if pan_match else 'Not Found',
        'DOB': dob_match.group() if dob_match else 'Not Found',
        'Name': cardholder_name,
        'Father’s Name': father_name
    }

def extract_aadhaar_details(text):
    aadhaar_pattern = r"\d{4}\s?\d{4}\s?\d{4}"
    dob_pattern = r"\d{2}/\d{2}/\d{4}"
    gender_pattern = r"\b(Male|Female|MALE|FEMALE|M|F)\b"

    aadhaar_match = re.search(aadhaar_pattern, text)
    dob_match = re.search(dob_pattern, text)
    gender_match = re.search(gender_pattern, text)

    lines = text.split('\n') if '\n' in text else text.split()
    lines = [line.strip() for line in lines if line.strip()]

    start_index = 0
    for i, line in enumerate(lines):
        if 'government of india' in line.lower():
            start_index = i
            break

    lines = lines[start_index+1:]  # skip the 'government of india' line itself

    name = 'Not Found'
    for line in lines:
        if line and not any(char.isdigit() for char in line) and 2 < len(line) < 40:
            name = line
            break

    gender = gender_match.group() if gender_match else 'Not Found'
    if gender.upper() == 'M':
        gender = 'Male'
    elif gender.upper() == 'F':
        gender = 'Female'

    return {
        'Type': 'Aadhaar',
        'Aadhaar No.': aadhaar_match.group() if aadhaar_match else 'Not Found',
        'DOB': dob_match.group() if dob_match else 'Not Found',
        'Name': name,
        'Gender': gender
    }

def process_document(image):
    img = cv2.imread(image)
    text = extract_text_from_image(image)

    if re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", text):
        result = extract_pan_details(text)
    else:
        result = extract_aadhaar_details(text)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if result['Type'] == 'PAN':
            cursor.execute("""
                INSERT INTO id_card_data (type, name, father_name, dob, pan_number, uploaded_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                result['Type'],
                result['Name'],
                result['Father’s Name'],
                datetime.strptime(result['DOB'], "%d/%m/%Y") if result['DOB'] != 'Not Found' else None,
                result['PAN No.'],
                datetime.now()
            ))

        elif result['Type'] == 'Aadhaar':
            cursor.execute("""
                INSERT INTO id_card_data (type, name, gender, dob, aadhaar_number, uploaded_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                result['Type'],
                result['Name'],
                result['Gender'],
                datetime.strptime(result['DOB'], "%d/%m/%Y") if result['DOB'] != 'Not Found' else None,
                result['Aadhaar No.'],
                datetime.now()
            ))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print("Database error:", e)

    return result


gr.Interface(
    fn=process_document,
    inputs=gr.Image(type="filepath", label="Upload Aadhaar or PAN Card"),
    outputs=gr.JSON(label="Extracted Information"),
    title="ID Card OCR Extractor",
    description="Upload an Aadhaar or PAN card image to extract details using OCR"
).launch()
