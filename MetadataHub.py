import streamlit as st
import pandas as pd
import exifread
import PyPDF2
import docx
import os
import tempfile
import piexif
from PIL import Image
from io import BytesIO
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Metadata Hub", layout="centered", page_icon="🗃️")
st.title("🗃️ Metadata Hub")
st.markdown("Drop your file, get the metadata, edit, and download the updated file or metadata CSV")

uploaded_file = st.file_uploader(
    "Upload a photo (JPEG/PNG), PDF, or Office document",
    type=["jpg", "jpeg", "png", "pdf", "docx", "xlsx", "mp3", "mp4"]
)

original_metadata = {}
edited_metadata = {}

def extract_image_metadata_and_gps(file_path):
    with open(file_path, 'rb') as f:
        tags = exifread.process_file(f, details=False)
        metadata = {tag: str(value) for tag, value in tags.items()}
        lat, lon = extract_gps_from_exif(tags)
    return metadata, lat, lon

def extract_pdf_metadata(file):
    reader = PyPDF2.PdfReader(file)
    info = reader.metadata
    return {key: str(info[key]) for key in info} if info else {}

def extract_docx_metadata(file_path):
    document = docx.Document(file_path)
    props = document.core_properties
    return {
        "author": props.author,
        "created": str(props.created),
        "last_modified_by": props.last_modified_by,
        "modified": str(props.modified),
        "title": props.title
    }

def save_metadata_to_csv(metadata_dict, filename):
    df = pd.DataFrame(list(metadata_dict.items()), columns=["Key", "Value"])
    csv_bytes = df.to_csv(index=False).encode()
    return csv_bytes

def extract_gps_from_exif(exif_tags):
    gps_latitude = exif_tags.get("GPS GPSLatitude")
    gps_latitude_ref = exif_tags.get("GPS GPSLatitudeRef")
    gps_longitude = exif_tags.get("GPS GPSLongitude")
    gps_longitude_ref = exif_tags.get("GPS GPSLongitudeRef")

    if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
        def dms_to_dd(dms, ref):
            degrees = float(dms.values[0].num) / float(dms.values[0].den)
            minutes = float(dms.values[1].num) / float(dms.values[1].den)
            seconds = float(dms.values[2].num) / float(dms.values[2].den)
            dd = degrees + (minutes / 60.0) + (seconds / 3600.0)
            if ref.values != "N" and ref.values != "E":
                dd = -dd
            return dd
        lat = dms_to_dd(gps_latitude, gps_latitude_ref)
        lon = dms_to_dd(gps_longitude, gps_longitude_ref)
        return lat, lon
    return None, None

def update_exif_bytes(original_bytes, edited_metadata):
    exif_dict = piexif.load(original_bytes)

    tag_map = {
        "Image Artist": ("0th", piexif.ImageIFD.Artist),
        "Image Make": ("0th", piexif.ImageIFD.Make),
        "Image Model": ("0th", piexif.ImageIFD.Model),
        "Image Software": ("0th", piexif.ImageIFD.Software),
        "Exif DateTimeOriginal": ("Exif", piexif.ExifIFD.DateTimeOriginal),
        "Exif UserComment": ("Exif", piexif.ExifIFD.UserComment),
    }

    for key, new_val in edited_metadata.items():
        if key in tag_map and new_val:
            ifd_name, tag_id = tag_map[key]
            exif_dict[ifd_name][tag_id] = new_val.encode('utf-8') + b'\x00'

    exif_bytes = piexif.dump(exif_dict)
    return exif_bytes

if uploaded_file:
    st.subheader("Extracted Metadata")
    extension = uploaded_file.name.split(".")[-1].lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_file_path = tmp_file.name

    try:
        lat, lon = None, None

        if extension in ["jpg", "jpeg", "png"]:
            original_metadata, lat, lon = extract_image_metadata_and_gps(tmp_file_path)

        elif extension == "pdf":
            with open(tmp_file_path, 'rb') as f:
                original_metadata = extract_pdf_metadata(f)

        elif extension == "docx":
            original_metadata = extract_docx_metadata(tmp_file_path)

        else:
            st.warning("That file type is supported for upload, but metadata extraction isn't implemented yet.")

        if original_metadata:
            st.sidebar.header("Filter Metadata Fields")
            selected_keys = st.sidebar.multiselect(
                "Select metadata fields to display and edit",
                options=list(original_metadata.keys()),
                default=list(original_metadata.keys())
            )

            st.subheader("Edit Metadata")
            for key in selected_keys:
                value = original_metadata.get(key, "")
                new_value = st.text_input(f"{key}", value)
                edited_metadata[key] = new_value

            st.write("### Edited Metadata Preview")
            st.json(edited_metadata)

            csv_original = save_metadata_to_csv(original_metadata, "original_metadata.csv")
            st.download_button(
                "Download Original Metadata CSV",
                data=csv_original,
                file_name="original_metadata.csv",
                mime="text/csv"
            )

            csv_edited = save_metadata_to_csv(edited_metadata, "edited_metadata.csv")
            st.download_button(
                "Download Edited Metadata CSV",
                data=csv_edited,
                file_name="edited_metadata.csv",
                mime="text/csv"
            )

            if extension in ["jpg", "jpeg"]:
                st.markdown("---")
                st.subheader("Download Edited Image with Updated Metadata")

                with open(tmp_file_path, "rb") as img_file:
                    original_img_bytes = img_file.read()

                try:
                    exif_bytes = update_exif_bytes(original_img_bytes, edited_metadata)

                    image = Image.open(BytesIO(original_img_bytes))

                    output_io = BytesIO()
                    image.save(output_io, "jpeg", exif=exif_bytes)
                    output_bytes = output_io.getvalue()

                    st.download_button(
                        label="Download Edited JPEG Image",
                        data=output_bytes,
                        file_name=f"edited_{uploaded_file.name}",
                        mime="image/jpeg"
                    )
                except Exception as e:
                    st.error(f"Error updating image EXIF metadata: {e}")

            if lat is not None and lon is not None:
                st.subheader("GPS Location Map")
                m = folium.Map(location=[lat, lon], zoom_start=15)
                folium.Marker([lat, lon], tooltip="Photo GPS Location").add_to(m)
                st_folium(m, width=700, height=450)
            else:
                st.info("No GPS location found in metadata.")

        else:
            st.warning("No metadata found or unable to extract.")

    except Exception as e:
        st.error(f"Error extracting metadata: {e}")

# Footer markdown
st.markdown("---")
st.markdown(
    "Developed for Metadata Hub — Streamlined metadata visibility and export.  \n"
    "Copyright © 2025 Samira Jawish ✨"
)
