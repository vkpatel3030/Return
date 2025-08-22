import os
import pandas as pd
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages 
import tempfile
import re

# ✅ Global variables to store data (simple solution)
uploaded_data = None
scanned_awbs = set()
matched_data = None
unmatched_data = None

# 🔹 Home Page
def home(request):
    return render(request, 'home.html')

# 🔹 Upload File
def upload_file(request):
    global uploaded_data
    table_html = None

    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']

        try:
            # ✅ Read file directly from memory (no temp file needed)
            if uploaded_file.name.endswith('.csv'):
                uploaded_data = pd.read_csv(uploaded_file, dtype=str, header=6)
            else:
                uploaded_data = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str, header=6)

            uploaded_data = uploaded_data.applymap(lambda x: str(x).strip())
            
            # ✅ Success message
            messages.success(request, "✅ File uploaded successfully!")

            # ✅ Convert to HTML table
            table_html = uploaded_data.to_html(classes="table table-bordered table-striped text-center", index=False)

        except Exception as e:
            messages.error(request, f"❌ Error reading file: {e}")

    return render(request, 'upload.html', {"table_html": table_html})

# 🔹 Scan AWB Numbers
def scan_awb(request):
    return render(request, "scan.html")

# 🔹 Save Scanned AWB Numbers
def save_scan(request):
    global scanned_awbs
    
    if request.method == 'POST':
        scanned_data = request.POST.get('scanned_data', '')
        new_awbs = set(awb.strip() for awb in scanned_data.replace('\n', ',').split(',') if awb.strip())

        # ✅ Store in global variable
        scanned_awbs.update(new_awbs)
        
        messages.success(request, f"✅ {len(new_awbs)} AWB numbers added!")
        return redirect('compare')

    return HttpResponse("Invalid Request", status=400)

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
    global uploaded_data, scanned_awbs, matched_data, unmatched_data
    
    try:
        # 1. Check if data exists
        if uploaded_data is None:
            messages.error(request, "❌ No file uploaded. Please upload a file first.")
            return redirect('upload_file')

        if not scanned_awbs:
            messages.error(request, "❌ No scanned AWB data found. Please scan AWB numbers first.")
            return redirect('scan_awb')

        # 2. Work with the uploaded data
        df = uploaded_data.copy()

        # 3. Try to find column with tracking links or AWBs
        if 'Tracking Link' in df.columns:  # 🔸 use tracking link if available
            df['__awb__'] = df['Tracking Link'].apply(extract_awb_from_url)
        elif 'AWB Number' in df.columns:  # 🔸 fallback to AWB Number column
            df['__awb__'] = df['AWB Number'].astype(str).str.strip()
        else:
            messages.error(request, "❌ AWB column not found in uploaded file.")
            return redirect('upload_file')

        # 4. Match
        df['Matched'] = df['__awb__'].isin(scanned_awbs)

        matched_data = df[df['Matched']].drop(columns=['Matched', '__awb__'])
        unmatched_data = df[~df['Matched']].drop(columns=['Matched', '__awb__'])

        messages.success(request, f"✅ Comparison completed! Matched: {len(matched_data)}, Unmatched: {len(unmatched_data)}")

        return render(request, 'result.html', {
            'matched_count': len(matched_data),
            'unmatched_count': len(unmatched_data)
        })

    except Exception as e:
        messages.error(request, f"❌ Error during comparison: {str(e)}")
        return redirect('upload_file')

# 🔹 Download Matched
def download_matched(request):
    global matched_data
    
    if matched_data is None or len(matched_data) == 0:
        messages.error(request, "⚠️ No matched data available.")
        return redirect('compare')

    try:
        # ✅ Create Excel file in memory
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            matched_data.to_excel(tmp_file.name, index=False)
            
            with open(tmp_file.name, "rb") as f:
                response = HttpResponse(
                    f.read(), 
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                response["Content-Disposition"] = 'attachment; filename="matched_parcels.xlsx"'
                
            # Clean up temp file
            os.unlink(tmp_file.name)
            return response
            
    except Exception as e:
        messages.error(request, f"❌ Error creating download file: {str(e)}")
        return redirect('compare')

# 🔹 Download Unmatched
def download_unmatched(request):
    global unmatched_data
    
    if unmatched_data is None or len(unmatched_data) == 0:
        messages.error(request, "⚠️ No unmatched data available.")
        return redirect('compare')

    try:
        # ✅ Create Excel file in memory
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            unmatched_data.to_excel(tmp_file.name, index=False)
            
            with open(tmp_file.name, "rb") as f:
                response = HttpResponse(
                    f.read(), 
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                response["Content-Disposition"] = 'attachment; filename="unmatched_parcels.xlsx"'
                
            # Clean up temp file
            os.unlink(tmp_file.name)
            return response
            
    except Exception as e:
        messages.error(request, f"❌ Error creating download file: {str(e)}")
        return redirect('compare')

# 🔹 Reset All Data (optional)
def reset_data(request):
    global uploaded_data, scanned_awbs, matched_data, unmatched_data
    
    uploaded_data = None
    scanned_awbs = set()
    matched_data = None
    unmatched_data = None
    
    messages.success(request, "✅ All data cleared!")
    return redirect('home')