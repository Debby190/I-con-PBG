import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from typing import Dict, List, Optional, Tuple
import io
import json

# ================================
# KONFIGURASI HALAMAN
# ================================
st.set_page_config(
    page_title="i-CON PBG - Internal Control",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================================
# KELAS UTAMA APLIKASI
# ================================
class PBGMonitoringApp:
    def __init__(self):
        self.SOP_TAHAPAN = {
            "VERIFIKASI BERKAS": 1,
            "SURVEY LOKASI": 2,
            "VERIFIKASI SUBKO": 3,
            "PENILAIAN TEKNIS TPT/TPA": 5,
            "MELENGKAPI PERBAIKAN BERKAS": 3,
            "PERHITUNGAN VOLUME": 1,
            "TTD GAMBAR KABID + KADIS": 2,
            "SCAN GAMBAR + BA TPT/TPA": 1,
            "PELAKSANAAN KONSULTASI + INPUT RETRIBUSI": 4,
            "SPPST KADIS": 1
        }
        self.df = None
        self.load_data()
        
    @st.cache_data(ttl=300)
    def load_data(_self):
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_info = st.secrets["google_credentials"]
        creds = Credentials.from_service_account_info(
            creds_info, 
            scopes=scope
        )

        client = gspread.authorize(creds)
        sheet = client.open_by_key("1LEKCe-bbye_mPx9pH-w22LOE95MqFD3ZEp5rLQoqVxg").sheet1

        df = pd.DataFrame(sheet.get_all_records())
        return df

    def hitung_status(self, row):
        """Hitung status permohonan berdasarkan tahapan"""
        tgl_registrasi = None
        
        # Ambil tanggal registrasi
        if pd.notna(row.get("TGL REGISTRASI")):
            try:
                tgl_registrasi = pd.to_datetime(row.get("TGL REGISTRASI"), dayfirst=True)
            except:
                pass
        
        # Cek SPPST KADIS
        sppst_val = row.get("SPPST KADIS")
        
        # Jika SPPST KADIS kosong atau tidak ada, masih diproses
        if pd.isna(sppst_val) or str(sppst_val).strip() == "":
            return "Diproses"
        
        # Jika SPPST KADIS isi "-", abaikan dan cek tahapan terakhir yang ada
        if str(sppst_val).strip() == "-":
            tahapan_list = [
                "VERIFIKASI BERKAS",
                "SURVEY LOKASI", 
                "VERIFIKASI SUBKO",
                "PENILAIAN TEKNIS TPT/TPA",
                "MELENGKAPI PERBAIKAN BERKAS",
                "PERHITUNGAN VOLUME",
                "TTD GAMBAR KABID + KADIS",
                "SCAN GAMBAR + BA TPT/TPA",
                "PELAKSANAAN KONSULTASI + INPUT RETRIBUSI",
                "SPPST KADIS"
            ]
            
            # Cari tahapan terakhir yang ada datanya (bukan kosong dan bukan "-")
            tgl_terakhir = None
            
            for tahap in reversed(tahapan_list):
                val = row.get(tahap)
                if pd.notna(val) and str(val).strip() != "" and str(val).strip() != "-":
                    try:
                        tgl_terakhir = pd.to_datetime(val, dayfirst=True)
                        break
                    except:
                        pass
            
            if tgl_terakhir and tgl_registrasi:
                total_hari = (tgl_terakhir - tgl_registrasi).days
                return "Tepat waktu" if total_hari <= 23 else "Terlambat"
            else:
                return "Diproses"
        
        # Jika SPPST KADIS ada tanggalnya, hitung dari TGL REGISTRASI
        try:
            tgl_sppst = pd.to_datetime(sppst_val, dayfirst=True)
            if tgl_registrasi:
                total_hari = (tgl_sppst - tgl_registrasi).days
                return "Tepat waktu" if total_hari <= 23 else "Terlambat"
            else:
                return "Diproses"
        except:
            return "Diproses"

    def highlight_terlambat(self, row):
        """Highlight berdasarkan SOP:
            - Setiap tahap dihitung dari tanggal tahap sebelumnya.
            - Tahap '-' tetap menambah akumulasi SOP.
            - Tahap dengan tanggal dibandingkan total SOP sejak tahap valid sebelumnya.
        """

        styles = [''] * len(row)

        tahapan = list(self.SOP_TAHAPAN.keys())

    # Ambil tanggal registrasi sebagai tahap awal
        try:
            prev_date = pd.to_datetime(row["TGL REGISTRASI"], dayfirst=True)
        except:
            return styles

        sop_acc = 0  # total SOP yang harus dipenuhi sejak prev_date

        for tahap in tahapan:
            col_idx = row.index.get_loc(tahap)
            sop_hari = self.SOP_TAHAPAN[tahap]
            nilai = str(row[tahap]).strip()

            # Jika tanggal TIDAK ada → hanya tambahkan SOP, prev_date tidak berubah
            if nilai == "-" or nilai == "":
                sop_acc += sop_hari
                continue

            # Jika tanggal ADA → hitung selisih
            try:
                curr_date = pd.to_datetime(nilai, dayfirst=True)
            except:
                # Jika format salah dianggap tidak valid
                sop_acc += sop_hari
                continue

            # Hitung selisih hari dari prev_date
            selisih = (curr_date - prev_date).days

            # Jika selisih > total SOP yang ditentukan dari beberapa tahap sebelumnya
            if selisih > sop_acc + sop_hari:
                styles[col_idx] = 'background-color: #fee2e2; color: #dc2626; font-weight: bold'

            # Setelah tahap selesai → reset akumulasi SOP
            sop_acc = 0
            prev_date = curr_date  # update ke tanggal tahap valid terbaru

        return styles


    def get_statistics(self) -> Dict:
        """Hitung statistik utama"""
        if self.df.empty:
            return {"total": 0, "selesai": 0, "diproses": 0, "terlambat": 0}
            
        if "STATUS" not in self.df.columns:
            return {"total": len(self.df), "selesai": 0, "diproses": 0, "terlambat": 0}
        
        total = len(self.df)
        return {
            "total": total,
            "selesai": len(self.df[self.df["STATUS"] == "Tepat waktu"]),
            "diproses": len(self.df[self.df["STATUS"] == "Diproses"]),
            "terlambat": len(self.df[self.df["STATUS"] == "Terlambat"])
        }

    def render_sidebar(self):
        """Render sidebar navigation"""
        with st.sidebar:
            # Header Sidebar - tanpa div wrapper
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image("logo_dinas-removebg-preview.png", width=150)
            
            # Teks langsung tanpa margin
            st.markdown("""
                <div style="text-align: center; margin-top: -10px;">
                    <div style="color: #1e293b; font-size: 14px; font-weight: 700; line-height: 1.5;">
                        Dinas Perumahan<br> 
                        Permukiman Cipta Karya<br>
                        dan Tata Ruang
                    </div>
                    <div style="color: #64748b; font-size: 11px; margin-top: 4px;">
                        Kabupaten Sidoarjo
                    </div>
                </div>
                <hr style="margin: 1rem 0; border: none; border-top: 2px solid #e2e8f0;">
            """, unsafe_allow_html=True)

            # Initialize session state
            if "menu_clicked" not in st.session_state:
                st.session_state["menu_clicked"] = "Beranda"

            # Menu items
            menu_items = [
                {"name": "Beranda", "icon": "🏠"},
                {"name": "Pencarian", "icon": "🔍"},
                {"name": "Monitoring", "icon": "📊"},
                {"name": "Laporan", "icon": "📄"}
                ]
            
            for item in menu_items:
                if st.button(f"{item['icon']}  {item['name']}", key=item['name'], use_container_width=True):
                    st.session_state["menu_clicked"] = item['name']
                    st.rerun()

            # Footer
            st.markdown("---")
            st.caption(f"📅 Update: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    def render_header(self):
        """Render header utama"""
    import base64
    
    # Encode logo
    try:
        with open("3.png", "rb") as f:
            encoded_logo = base64.b64encode(f.read()).decode()
    except:
        encoded_logo = ""
    
    st.markdown(f"""
<div class="main-header">
    <div class="header-content">
        <div class="header-left">
            <div class="logo-container">
                <img src="data:image/png;base64,{encoded_logo}" style="width: 100%; height: 100%; object-fit: contain; border-radius: 50%">
            </div>
            <div class="header-title">
                <h1>i-CON PBG</h1>
                <p>Internal Control - Persetujuan Bangunan Gedung</p>
            </div>
        </div>
        <div class="admin-badge">👤 Admin</div>
    </div>
</div>
""", unsafe_allow_html=True)

    def render_beranda(self):
        """Render halaman beranda"""
        st.markdown("""
        <div class="page-title-card">
            <h2>Dashboard Beranda</h2>
            <p>Ringkasan dan overview status permohonan PBG</p>
        </div>
        """, unsafe_allow_html=True)
        
        stats = self.get_statistics()
        
        # Metric Cards - 4 kolom
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #3b82f6;">
                <div class="metric-icon">📋</div>
                <div class="metric-value" style="color: #3b82f6;">{stats.get('total', 0)}</div>
                <div class="metric-label">Total Permohonan</div> 
           </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #f59e0b;">
                <div class="metric-icon">⏳</div>
                <div class="metric-value" style="color: #f59e0b;">{stats.get('diproses', 0)}</div>
                <div class="metric-label">Sedang Diproses</div> 
           </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #10b981;">
                <div class="metric-icon">✅</div>
                <div class="metric-value" style="color: #10b981;">{stats.get('selesai', 0)}</div>
                <div class="metric-label">Tepat Waktu</div>
           </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #ef4444;">
                <div class="metric-icon">⚠️</div>
                <div class="metric-value" style="color: #ef4444;">{stats.get('terlambat', 0)}</div>
                <div class="metric-label">Terlambat</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Charts Section - 2 kolom
        col_chart, col_activity = st.columns([2, 2])
        
        # === KOLOM KIRI: PIE CHART ===
        with col_chart:
            st.markdown("""
            <div class="chart-card">
                <h3>📊 Distribusi Status Permohonan</h3>
                <p>Proporsi berdasarkan status terkini</p>
            </div>
            """, unsafe_allow_html=True)
            
            status_counts = self.df["STATUS"].value_counts()
            colors = {
                'Tepat waktu': '#10b981',
                'Diproses': '#f59e0b',
                'Terlambat': '#ef4444'
            }
            
            fig = go.Figure(data=[go.Pie(
                labels=status_counts.index,
                values=status_counts.values,
                hole=0.55,
                marker=dict(
                    colors=[colors.get(x, '#94a3b8') for x in status_counts.index],
                    line=dict(color='white', width=3)
                ),
                textposition='none',  
                hovertemplate='<b style="font-size:14px">%{label}</b><br>' +
                            'Jumlah: <b>%{value}</b><br>' +
                            'Persentase: <b>%{percent}</b><extra></extra>',
                hoverlabel=dict(
                    bgcolor='white',
                    font=dict(size=13, color='#1e293b', family='Inter'),
                    bordercolor='#e2e8f0'
                )
            )])
            
            fig.update_layout(
                showlegend=False,
                height=320,
                margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(family='Inter', size=13, color='#1e293b'),
                annotations=[dict(
                    text=f'<b style="font-size:32px; color:#1e293b">{stats.get("total", 0)}</b><br>' +
                        '<span style="font-size:14px; color:#64748b">Total</span><br>' +
                        '<span style="font-size:14px; color:#64748b">Permohonan</span>',
                    x=0.5,
                    y=0.5,
                    font_size=16,
                    showarrow=False,
                    align='center'
                )]
            )
            
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
        
        # === KOLOM KANAN: AKTIVITAS TERBARU ===
        with col_activity:
            st.markdown("""
            <div class="activity-card-header">
                <h3>📢 Aktivitas Terbaru</h3>
                <p>Permohonan yang perlu perhatian</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Filter data: prioritaskan Terlambat, lalu Diproses
            self.df["TGL REGISTRASI"] = pd.to_datetime(self.df["TGL REGISTRASI"], errors="coerce")
            
            # Ambil data terlambat dan diproses saja
            df_priority = self.df[self.df["STATUS"].isin(["Terlambat", "Diproses"])].copy()
            
            # Sort: Terlambat dulu, lalu tanggal terbaru
            df_priority["sort_priority"] = df_priority["STATUS"].map({"Diproses": 1, "Terlambat": 2})
            df_sorted = df_priority.sort_values(["sort_priority", "TGL REGISTRASI"], ascending=[True, False]).head(5)
            
            if len(df_sorted) == 0:
                st.markdown("""
                <div class="empty-activity">
                    <div style="text-align: center; padding: 2rem 1rem; color: #94a3b8;">
                        <div style="font-size: 40px; margin-bottom: 12px;">✨</div>
                        <div style="font-size: 12px; font-weight: 600; color: #64748b;">Tidak ada permohonan yang memerlukan perhatian</div>
                        <div style="font-size: 10px; color: #94a3b8; margin-top: 4px;">Semua permohonan telah selesai tepat waktu</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown('<div class="activity-container">', unsafe_allow_html=True)
                
                for idx, row in df_sorted.iterrows():
                    status = row["STATUS"]
                    nama_pemohon = row.get("NAMA PEMOHON", "-")
                    tgl_reg = row["TGL REGISTRASI"]
                    
                    # Format tanggal
                    if pd.notna(tgl_reg):
                        tgl_formatted = tgl_reg.strftime("%d/%m/%Y")
                    else:
                        tgl_formatted = "-"
                    
                    # Icon dan warna berdasarkan status
                    if status == "Diproses":
                        icon = "⏳"
                        color = "#f59e0b"
                        bg_color = "#fffbeb"
                        border_color = "#f59e0b"
                    else:  # Terlambat
                        icon = "⚠️"
                        color = "#ef4444"
                        bg_color = "#fef2f2"
                        border_color = "#ef4444"
                    
                    st.markdown(f"""
                    <div class="activity-item-card" style="
                        background: {bg_color};
                        border-left: 3px solid {border_color};
                        padding: 10px 12px;
                        margin-bottom: 10px;
                        border-radius: 8px;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
                    ">
                        <div style="display: flex; align-items: flex-start; gap: 10px;">
                            <div style="
                                width: 32px;
                                height: 32px;
                                background: white;
                                border-radius: 6px;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                font-size: 16px;
                                flex-shrink: 0;
                                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
                            ">
                                {icon}
                            </div>
                            <div style="flex: 1; min-width: 0;">
                                <div style="
                                    color: #1e293b;
                                    font-size: 11px;
                                    font-weight: 700;
                                    margin-bottom: 3px;
                                    white-space: nowrap;
                                    overflow: hidden;
                                    text-overflow: ellipsis;
                                ">
                                    {row['NO. REGISTRASI']}
                                </div>
                                <div style="
                                    color: #64748b;
                                    font-size: 10px;
                                    margin-bottom: 5px;
                                    white-space: nowrap;
                                    overflow: hidden;
                                    text-overflow: ellipsis;
                                ">
                                    {nama_pemohon}
                                </div>
                                <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px;">
                                    <span style="
                                        background: {color};
                                        color: white;
                                        padding: 2px 8px;
                                        border-radius: 10px;
                                        font-size: 9px;
                                        font-weight: 600;
                                        white-space: nowrap;
                                    ">
                                        {status}
                                    </span>
                                    <span style="
                                        color: #94a3b8;
                                        font-size: 9px;
                                        font-weight: 500;
                                    ">
                                        📅 {tgl_formatted}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)

    def render_pencarian(self):
        """Render halaman pencarian"""
        st.markdown("""
        <div class="page-title-card">
            <h2>🔍 Pencarian Data Permohonan</h2>
            <p>Cari dan filter data permohonan berdasarkan kriteria</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            search_option = st.selectbox(
                "Cari berdasarkan:",
                ["NO. REGISTRASI", "NAMA PEMOHON", "VERIFIKATOR",
                 "SURVEY SUBKO", "PENILAI TEKNIS TPT/TPA"]
            )

        with col2:
            search_input = st.text_input("Masukkan kata kunci", "")
        
        with col3:
            status_filter = st.multiselect(
                "Filter Status:",
                ["Tepat waktu", "Diproses", "Terlambat"],
                default=["Tepat waktu", "Diproses", "Terlambat"]
            )
                    
        # Proses pencarian
        result = self.df.copy()
        
        # Filter berdasarkan kata kunci
        if search_input.strip():
            if search_option == "STATUS":
                result = result[result["STATUS"].str.contains(search_input, case=False, na=False)]
            else:
                result = result[result[search_option].astype(str).str.contains(search_input, case=False, na=False)]
        
        if result.empty:
            st.warning("⚠️ Tidak ada data yang cocok dengan kriteria pencarian.")
            return

        # Hitung total hari
        def hitung_total_hari(row):
            try:
                tgl_reg = pd.to_datetime(row["TGL REGISTRASI"], dayfirst=True)
                tgl_sppst = pd.to_datetime(row["SPPST KADIS"], dayfirst=True)
                return (tgl_sppst - tgl_reg).days
            except:
                return None

        result["TOTAL HARI"] = result.apply(hitung_total_hari, axis=1).astype('Int64')

        # Tampilkan hasil
        st.success(f"✅ Ditemukan {len(result)} hasil pencarian")

        st.dataframe(
            result.style.apply(self.highlight_terlambat, axis=1),
            use_container_width=True,
            height=400
        )

        st.markdown("""
        <div class="legend-box">
            <span class="legend-item">Merah</span>
            <span style="font-size: 13px; color: #64748b;">
                = Tahapan melebihi akumulasi waktu SOP dari tanggal registrasi
            </span>
        </div>
        """, unsafe_allow_html=True)

    def render_monitoring(self):
        """Render halaman monitoring"""
        st.markdown("""
        <div class="page-title-card">
            <h2> Monitoring Permohonan</h2>
            <p>Grafik tren permohonan per periode</p>
        </div>
        """, unsafe_allow_html=True)

        if "TGL REGISTRASI" in self.df.columns:

            df_mon = self.df.copy()

        # Konversi tanggal dd-mm-yyyy
            df_mon["TGL REGISTRASI"] = pd.to_datetime(
                df_mon["TGL REGISTRASI"], 
                dayfirst=True, 
                errors="coerce"
            )

        # Filter hanya yg ada tanggal
            df_mon = df_mon[df_mon["TGL REGISTRASI"].notna()].copy()

        # Info jumlah data valid
            st.info(f"ℹ️ Total data yang memiliki tanggal registrasi: **{len(df_mon)}** dari {len(self.df)} permohonan")

        # ============ FILTER TAHUN ============
            tahun_list = sorted(df_mon["TGL REGISTRASI"].dt.year.unique())

            pilih_tahun = st.selectbox(
                "📅 Pilih Tahun Permohonan",
                options=["Semua Tahun"] + list(map(str, tahun_list)),
                index=0
            )

        # Terapkan filter tahun
            if pilih_tahun != "Semua Tahun":
                df_mon = df_mon[df_mon["TGL REGISTRASI"].dt.year == int(pilih_tahun)]

        # ======================================

        # Buat kolom bulan
            df_mon["Bulan"] = df_mon["TGL REGISTRASI"].dt.to_period("M").astype(str)

        # Hitung jumlah per bulan per status
            monthly_counts = df_mon.groupby(["Bulan", "STATUS"]).size().reset_index(name="Jumlah")

        # Sort
            monthly_counts["Sort_Date"] = pd.to_datetime(monthly_counts["Bulan"], format="%Y-%m")
            monthly_counts = monthly_counts.sort_values("Sort_Date")

        # Judul grafik dinamis
            judul_grafik = (
                f"Tren Permohonan Bulanan - Tahun {pilih_tahun}"
                if pilih_tahun != "Semua Tahun"
                else "Tren Permohonan Bulanan - Semua Tahun"
            )

        # ============ GRAFIK ============

            fig = px.bar(
                monthly_counts,
                x="Bulan",
                y="Jumlah",
                color="STATUS",
                barmode="group",
                color_discrete_map={
                    "Tepat waktu": "#10b981",
                    "Diproses": "#f59e0b",
                    "Terlambat": "#ef4444"
                },
                text="Jumlah",
                title=judul_grafik
            )

            fig.update_traces(textposition="outside", textfont_size=11)

            fig.update_layout(
                height=500,
                font=dict(family="Inter", size=12),
                margin=dict(t=60, b=60, l=60, r=40),
                hovermode="x unified",
                yaxis_title="Jumlah Permohonan",
                xaxis_title="Periode (Bulan-Tahun)",
                legend_title="Status",
                plot_bgcolor="white",
                paper_bgcolor="white",
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.2,
                    xanchor="center",
                    x=0.5
                )
            )

            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True})

        # ============ RINGKASAN ============

            total_data_monitoring = len(df_mon)
            tepat_waktu = len(df_mon[df_mon["STATUS"] == "Tepat waktu"])
            diproses = len(df_mon[df_mon["STATUS"] == "Diproses"])
            terlambat = len(df_mon[df_mon["STATUS"] == "Terlambat"])

            pct_tepat = (tepat_waktu / total_data_monitoring * 100) if total_data_monitoring else 0
            pct_diproses = (diproses / total_data_monitoring * 100) if total_data_monitoring else 0
            pct_terlambat = (terlambat / total_data_monitoring * 100) if total_data_monitoring else 0

            st.markdown(f"""
            <div class="info-box">
                📊 <strong>Info Data Monitoring:</strong><br>
                <strong>Total: {total_data_monitoring} permohonan</strong> | 
                <span style="color: #10b981; font-weight: 600;">✅ Tepat Waktu: {tepat_waktu} ({pct_tepat:.1f}%)</span> | 
                <span style="color: #f59e0b; font-weight: 600;">⏳ Diproses: {diproses} ({pct_diproses:.1f}%)</span> | 
                <span style="color: #ef4444; font-weight: 600;">⚠️ Terlambat: {terlambat} ({pct_terlambat:.1f}%)</span>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.error("⚠️ Kolom 'TGL REGISTRASI' tidak ditemukan dalam data")


    def render_laporan(self):
        """Render halaman laporan"""
        st.markdown("""
        <div class="page-title-card">
            <h2>📄 Laporan & Ekspor Data</h2>
            <p>Filter data berdasarkan rentang tanggal dan ekspor ke CSV</p>
        </div>
        """, unsafe_allow_html=True)
    
        col1, col2, col3 = st.columns([2, 2, 1])
    
        with col1:
            start_date = st.date_input(
                "📅 Tanggal Mulai",
                datetime.now() - timedelta(days=30)
        )
    
        with col2:
            end_date = st.date_input(
                "📅 Tanggal Akhir",
                datetime.now()
           )
    
        with col3:
            tampilkan = st.button("📊 Tampilkan", use_container_width=True)
    
        if tampilkan:

        # 🔥🔥 PERBAIKAN FORMAT TANGGAL YANG BENAR 🔥🔥
            self.df["TGL REGISTRASI"] = pd.to_datetime(
                self.df["TGL REGISTRASI"].astype(str),
                dayfirst=True,          # <= Fix utama
                errors="coerce"
            )

        # Konversi dari date_input ke datetime
            start_date = pd.to_datetime(start_date)
            end_date = pd.to_datetime(end_date)

        # Filtering data
            df_filtered = self.df[
                (self.df["TGL REGISTRASI"] >= start_date) & 
                (self.df["TGL REGISTRASI"] <= end_date)
            ]
        
            if not df_filtered.empty:
            # Summary metrics
                col_sum1, col_sum2, col_sum3, col_sum4, col_sum5 = st.columns(5)
            
                filtered_total = len(df_filtered)
                filtered_selesai = len(df_filtered[df_filtered["STATUS"] == 'Tepat waktu'])
                filtered_diproses = len(df_filtered[df_filtered["STATUS"] == "Diproses"])
                filtered_terlambat = len(df_filtered[df_filtered["STATUS"] == "Terlambat"])
                # filtered_presentasi = len(df_filtered[df_filtered['STATUS'] == 'Tepat waktu']) / len(df_filtered) * 100
                filtered_presentasi = f"{(len(df_filtered[df_filtered['STATUS'] == 'Tepat waktu']) / len(df_filtered) * 100):.1f}%"

                with col_sum1:
                    st.metric("Total Permohonan", filtered_total)
                with col_sum2:
                    st.metric("Tepat Waktu", filtered_selesai)
                with col_sum3:
                    st.metric("Diproses", filtered_diproses)
                with col_sum4:
                    st.metric("Terlambat", filtered_terlambat, delta_color="inverse")
                with col_sum5:
                    st.metric("Prosentase", filtered_presentasi)
            
                st.markdown("<br>", unsafe_allow_html=True)
            
                st.success(f"✅ Ditemukan **{filtered_total}** permohonan dalam periode yang dipilih")
            
                st.dataframe(
                    df_filtered.style.apply(self.highlight_terlambat, axis=1),
                    use_container_width=True,
                    height=400
                )
            
                st.markdown("""
                <div class="legend-box">
                    <span class="legend-item">Merah</span>
                    <span style="font-size: 13px; color: #64748b;">
                        = Tahapan melebihi akumulasi waktu SOP dari tanggal registrasi
                    </span>
                /div>
                """, unsafe_allow_html=True)
            
            # ================================
            # ONLY DOWNLOAD LAPORAN
            # ================================
            csv = df_filtered.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download Laporan (CSV)",
                data=csv,
                file_name=f"Laporan_PBG_{start_date}_to_{end_date}.csv",
                mime="text/csv",
                use_container_width=True
            )

        else:
            st.warning("⚠️ Tidak ada data dalam rentang tanggal yang dipilih")

    def run(self):
        """Jalankan aplikasi utama"""
        # Load data
        self.df = self.load_data()
        if "STATUS" not in self.df.columns:
            self.df["STATUS"] = self.df.apply(self.hitung_status, axis=1)
        else:
            # Jika ada tapi kosong, regenerasi
            if self.df["STATUS"].isna().all() or (self.df["STATUS"] == "").all():
                self.df["STATUS"] = self.df.apply(self.hitung_status, axis=1)
        
        # Render komponen
        self.render_sidebar()
        self.render_header()
        
        # Render halaman berdasarkan menu
        current_menu = st.session_state.get("menu_clicked", "Beranda")
        
        if current_menu == "Beranda":
            self.render_beranda()
        elif current_menu == "Pencarian":
            self.render_pencarian()
        elif current_menu == "Monitoring":
            self.render_monitoring()
        elif current_menu == "Laporan":
            self.render_laporan()

# ================================
# CSS STYLING (Tetap sama seperti sebelumnya)
# ================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

* {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: #f8fafc;
}

/* Header */
.main-header {
    background: linear-gradient(135deg, #0094E8 0%, #0077BE 100%);
    padding: 1.5rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 8px 24px rgba(0, 148, 232, 0.2);
}

.header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 1.5rem;
}

.logo-container {
    width: 100px;
    height: 100px;
    background: white;
    border-radius: 50%;
    border: 4px solid black;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    overflow: hidden; /* Tambahkan ini untuk mencegah gambar keluar */
}

.logo-container img {
    width: 100%;
    height: 100%;
    object-fit: contain; /* Pastikan gambar proporsional */
    display: block;
}

.header-title h1 {
    color: white;
    font-size: 28px;
    font-weight: 800;
    margin: 0;
    letter-spacing: 0.5px;
}

.header-title p {
    color: rgba(255, 255, 255, 0.9);
    font-size: 13px;
    margin: 4px 0 0 0;
    font-weight: 500;
}

.admin-badge {
    background: rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(10px);
    padding: 10px 24px;
    border-radius: 25px;
    font-size: 13px;
    font-weight: 600;
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.3);
}

.search-container {
    display: flex;
    align-items: center;
    background: white;
    border-radius: 8px;
    border: 1px solid #d1d5db;
    padding: 6px 10px;
}

.search-input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 14px;
}

.search-button {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 18px;
    color: #1e293b;
}

.search-button:hover {
    color: #0094E8;
    transform: scale(1.1);
}


/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f8fafc 0%, #0094E8 100%);
    border-right: 1px solid #e2e8f0;
}

.sidebar-header {
    text-align: center;
    padding: 1.5rem 1rem;
    border-bottom: 2px solid #e2e8f0;
    margin-bottom: 1rem;
}

.sidebar-logo {
    width: 70px;
    height: 70px;
    margin: 0 auto 1rem;
    filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.1));
}

.sidebar-title {
    color: #1e293b;
    font-size: 14px;
    font-weight: 700;
    line-height: 1.5;
}

.sidebar-subtitle {
    color: #64748b;
    font-size: 11px;
    margin-top: 4px;
}

[data-testid="stSidebar"] .stButton button {
    background: white !important;
    color: #475569 !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    padding: 14px 18px !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    text-align: left !important;
    margin-bottom: 8px !important;
    transition: all 0.3s ease !important;
    width: 100% !important;
}

[data-testid="stSidebar"] .stButton button:hover {
    background: #0094E8 !important;
    color: white !important;
    border-color: #0094E8 !important;
    transform: translateX(4px);
    box-shadow: 0 4px 12px rgba(0, 148, 232, 0.2);
}

/* Page Title Card */
.page-title-card {
    background: white;
    padding: 1.2rem 1.5rem;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    margin-bottom: 1.5rem;
    border-left: 4px solid #0094E8;
}

.page-title-card h2 {
    font-size: 20px;
    margin: 0;
    font-weight: 700;
    color: #1e293b;
}

.page-title-card p {
    font-size: 12px;
    margin: 6px 0 0 0;
    color: #64748b;
    font-weight: 500;
}

/* Metric Cards */
.metric-card {
    background: white;
    padding: 1.2rem;
    border-radius: 12px;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    border-left: 4px solid;
    transition: all 0.3s ease;
    margin-bottom: 10px;
}

.metric-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
}

.metric-icon {
    font-size: 20px;
    margin-bottom: 2px;
}

.metric-label {
    font-size: 11px;
    color: #475569;
    font-weight: 600;
    margin-bottom: 3px;
}

.metric-value {
    font-size: 20px;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 5px;
}

/* Content Box */
.content-box {
    background: white;
    padding: 1.2rem;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.activity-item {
    padding: 12px;
    border-bottom: 1px solid #f1f5f9;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 10px;
}

.activity-item:last-child {
    border-bottom: none;
}

/* Info Box */
.info-box {
    background: #f0f9ff;
    border-left: 4px solid #0094E8;
    padding: 1rem 1.2rem;
    border-radius: 8px;
    margin-top: 1rem;
    font-size: 12px;
    color: #0c4a6e;
}

/* Legend */
.legend-box {
    background: white;
    padding: 12px 16px;
    border-radius: 8px;
    margin-top: 1rem;
    border: 1px solid #e2e8f0;
}

.legend-item {
    display: inline-block;
    background: #fee2e2;
    color: #dc2626;
    padding: 4px 12px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 12px;
    margin-right: 8px;
}

/* Table Styling */
.dataframe {
    font-size: 11px !important;
}

/* Footer */
.sidebar-footer {
    position: absolute;
    bottom: 20px;
    left: 0;
    right: 0;
    padding: 0 1rem;
    text-align: center;
    font-size: 11px;
    color: #94a3b8;
}

.divider {
    height: 5px;
    background: linear-gradient(90deg, transparent, #0094E8, transparent);
    margin: 1.5rem 0;
    border: none;
}
</style>
<script>
document.body.style.zoom = "0.75";   
</script>
""", unsafe_allow_html=True)

# ================================
# JALANKAN APLIKASI
# ================================
if __name__ == "__main__":
    app = PBGMonitoringApp()

    app.run()






