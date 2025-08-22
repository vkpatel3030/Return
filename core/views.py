import os
import pandas as pd
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.conf import settings
from .models import UploadedFile, ScannedAWB
from django.core.files.storage import FileSystemStorage
from django.contrib import messages 

# 🔹 Home Page
def home(request):
    return render(request, 'home.html')

# 🔹 Upload File
def upload_file(request):
    table_html = None

    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']

        # ✅ Temporary save in /tmp/
        temp_path = os.path.join(settings.BASE_DIR, 'tmp_uploaded_file.xlsx')
        with open(temp_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        # ✅ Success message
        messages.success(request, "✅ File uploaded successfully!")

        # ✅ Read Excel/CSV data & convert to HTML table
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(temp_path)
            else:
                df = pd.read_excel(temp_path)

            table_html = df.to_html(classes="table table-bordered table-striped text-center", index=False)

        except Exception as e:
            messages.error(request, f"❌ Error reading file: {e}")

    return render(request, 'upload.html', {"table_html": table_html})

# 🔹 Scan AWB Numbers
def scan_awb(request):
    return render(request, "scan.html")

# 🔹 Save Scanned AWB Numbers
def save_scan(request):
    if request.method == 'POST':
        scanned_data = request.POST.get('scanned_data', '')
        new_awbs = set(awb.strip() for awb in scanned_data.replace('\n', ',').split(',') if awb.strip())

        file_path = os.path.join(settings.MEDIA_ROOT, 'scanned_awbs.txt')
        existing_awbs = set()

        # Read old AWB numbers if file exists
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        if ',' in line:
                            existing_awbs.update(x.strip() for x in line.split(','))
                        else:
                            existing_awbs.add(line)

        # Combine old and new without duplicates
        combined_awbs = existing_awbs.union(new_awbs)

        # Save final combined list back to file
        with open(file_path, 'w') as f:
            for awb in combined_awbs:
                f.write(f"{awb}\n")

        return redirect('compare')

    return HttpResponse("Invalid Request", status=400)
def get_latest_uploaded_file():
    upload_folder = os.path.join(settings.MEDIA_ROOT, 'uploads')
    if not os.path.exists(upload_folder):
        return None

    files = [os.path.join(upload_folder, f) for f in os.listdir(upload_folder)
             if os.path.isfile(os.path.join(upload_folder, f)) and f.endswith(('.xlsx', '.xls', '.csv'))]
    if not files:
        return None

    latest_file = max(files, key=os.path.getctime)
    return latest_file

import re  # 🎯 NEW: For regex-based AWB extraction from Tracking Link

import os
import pandas as pd
import re
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse

# 🎯 AWB Extractor from any tracking link
def extract_awb_from_url(url):
    if not isinstance(url, str):
        return ''
     
    patterns = [
        r'trackingId=([A-Z0-9]+)',              # Shadowfax
        r'refNum=([A-Z0-9]+)',                  # Meesho
        r'trackid=([0-9]+)',                    # XpressBees
        r'/([A-Z0-9]{10,})$',                   # Valmo, fallback
        r'/package/([0-9]+)',                   # Delhivery
    ]
    for pattern in patterns:
        match = re.search(pattern, str(url))
        if match:
            return match.group(1)
    return url.strip()

# 🔹 Compare Data
def compare_data(request):
    try:
        # 1. Load latest uploaded file
        latest_file = get_latest_uploaded_file()
        if not latest_file:
            return HttpResponse("No file uploaded.")

        ext = os.path.splitext(latest_file)[1]
        if ext == '.csv':
            df = pd.read_csv(latest_file, dtype=str, header=6)
        else:
            df = pd.read_excel(latest_file, engine='openpyxl', dtype=str, header=6)

        df = df.applymap(lambda x: str(x).strip())

        # 2. Load scanned AWBs
        scanned_file = os.path.join(settings.MEDIA_ROOT, 'scanned_awbs.txt')
        if not os.path.exists(scanned_file):
            return HttpResponse("No scanned AWB data found.")

        with open(scanned_file, 'r') as f:
            content = f.read()
            if ',' in content:
                scanned_awbs = [awb.strip() for awb in content.split(',') if awb.strip()]
            else:
                scanned_awbs = [awb.strip() for awb in content.strip().split('\n') if awb.strip()]
        scanned_awbs_set = set([x.strip() for x in scanned_awbs if x])

        # 3. Try to find column with tracking links or AWBs
        if 'Tracking Link' in df.columns:  # 🔸 use tracking link if available
            df['__awb__'] = df['Tracking Link'].apply(extract_awb_from_url)
        elif 'AWB Number' in df.columns:  # 🔸 fallback to AWB Number column
            df['__awb__'] = df['AWB Number'].astype(str).str.strip()
        else:
            return HttpResponse("AWB column not found.")

        # 4. Match
        df['Matched'] = df['__awb__'].isin(scanned_awbs_set)

        matched_df = df[df['Matched']].drop(columns=['Matched'])
        unmatched_df = df[~df['Matched']].drop(columns=['Matched'])

        # 5. Save Excel
        matched_path = os.path.join(settings.MEDIA_ROOT, 'matched.xlsx')
        unmatched_path = os.path.join(settings.MEDIA_ROOT, 'unmatched.xlsx')
        matched_df.to_excel(matched_path, index=False)
        unmatched_df.to_excel(unmatched_path, index=False)

        # 6. Store to session
        request.session['matched'] = matched_df.to_dict(orient='records')
        request.session['unmatched'] = unmatched_df.to_dict(orient='records')

        return render(request, 'result.html', {
            'matched_count': len(matched_df),
            'unmatched_count': len(unmatched_df)
        })

    except Exception as e:
        return HttpResponse(f"Error: {str(e)}")


# 🔹 Download Matched
def download_matched(request):
    matched = request.session.get("matched", [])
    if not matched:
        return HttpResponse("⚠️ No matched data available.")

    df = pd.DataFrame(matched)
    file_path = os.path.join("/tmp", "matched.xlsx")
    df.to_excel(file_path, index=False)

    with open(file_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="matched.xlsx"'
        return response

# 🔹 Download Unmatched
def download_unmatched(request):
    unmatched = request.session.get("unmatched", [])
    if not unmatched:
        return HttpResponse("⚠️ No unmatched data available.")

    df = pd.DataFrame(unmatched)
    file_path = os.path.join("/tmp", "unmatched.xlsx")
    df.to_excel(file_path, index=False)

    with open(file_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="unmatched.xlsx"'
        return response
