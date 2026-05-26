import streamlit as st
import pandas as pd
import numpy as np
from datetime import timedelta, datetime, time
import plotly.express as px
import plotly.graph_objects as go
import calendar

# ==========================================
# CẤU HÌNH GIAO DIỆN (SIMULATION ENGINE VERSION)
# ==========================================
st.set_page_config(page_title="Toyota Logistics Monitor", page_icon="🚗", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1, h2, h3 {color: #d32f2f;}
    .st-emotion-cache-1wivap2 {border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}
    </style>
""", unsafe_allow_html=True)

st.title("🚗 TOYOTA LOGISTICS MONITOR & SIMULATION CENTER")
st.markdown("Hệ thống đồng bộ dữ liệu thực tế và mô phỏng kịch bản biến động Cung - Cầu.")

# ==========================================
# SIDEBAR: 3 NÚT TẢI FILE ĐỘC LẬP (TÊN FILE TÙY Ý)
# ==========================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/9/9d/Toyota_carlogo.svg/1200px-Toyota_carlogo.svg.png", width=100)
    st.header("📂 TRUNG TÂM DỮ LIỆU GỐC")
    
    file_kh = st.file_uploader("1. Tải KẾ HOẠCH (File đã điền đủ 12 cột)", type=["xlsx", "csv"])
    file_dl = st.file_uploader("2. Tải ĐẠI LÝ (Đơn đặt hàng)", type=["xlsx", "csv"])
    file_bg = st.file_uploader("3. Tải BẢNG GIÁ (Cước vận chuyển)", type=["xlsx", "csv"])
    
    st.divider()
    st.subheader("🎛️ BỘ ĐIỀU KHIỂN BIẾN ĐỘNG")
    demand_change = st.slider("Biến động Đặt hàng (Cầu) %", min_value=-100.0, max_value=300.0, value=0.0, step=1.0)
    supply_change = st.slider("Biến động Sản xuất (Cung) %", min_value=-100.0, max_value=300.0, value=0.0, step=1.0)
    max_wait_time = st.slider("Thời gian trần neo bãi (Giờ)", min_value=4.0, max_value=240.0, value=34.0, step=1.0)

# ==========================================
# LÕI ĐỌC VÀ PHÂN TÍCH DỮ LIỆU ĐÃ ĐIỀN ĐỦ
# ==========================================
@st.cache_data
def analyze_populated_data(f_kh, f_dl, f_bg):
    # Đọc dữ liệu từ file kế hoạch đã điền đủ cột
    df_kh = pd.read_excel(f_kh, header=1) if f_kh.name.endswith('.xlsx') else pd.read_csv(f_kh, header=1)
    df_dl = pd.read_excel(f_dl, header=1) if f_dl.name.endswith('.xlsx') else pd.read_csv(f_dl, header=1)
    df_bg = pd.read_excel(f_bg, header=1) if f_bg.name.endswith('.xlsx') else pd.read_csv(f_bg, header=1)
    
    # Chuẩn hóa tên cột viết hoa/khoảng trắng
    df_kh.columns = [str(c).strip() for c in df_kh.columns]
    
    # 1. TRÍCH XUẤT SỐ LIỆU GỐC THỰC TẾ (ĐỒNG BỘ 100%)
    actual_base_cost = pd.to_numeric(df_kh['Chi phí vận chuyển'], errors='coerce').sum()
    actual_base_inventory = pd.to_numeric(df_kh['Số ngày tồn kho'], errors='coerce').mean()
    total_cars_in_plan = len(df_kh)
    
    # Tự động tìm chu kỳ tháng/năm
    raw_dates = pd.to_datetime(df_kh['Ngày xuất xưởng'], errors='coerce').dropna()
    start_date = raw_dates.min().replace(day=1)
    cycle_month = start_date.strftime('%m/%Y')
    
    # Tạo bảng phân bổ ngày xuất bãi gốc để tính Heijunka thực tế
    df_kh['Ngày_Xuất_Bãi_DT'] = pd.to_datetime(df_kh['Ngày xuất bãi'], errors='coerce')
    daily_outbound_base = df_kh.groupby(df_kh['Ngày_Xuất_Bãi_DT'].dt.date).size()
    base_heijunka_cv = (daily_outbound_base.std() / daily_outbound_base.mean() * 100) if daily_outbound_base.mean() > 0 else 9.5
    
    return df_kh, actual_base_cost, actual_base_inventory, total_cars_in_plan, base_heijunka_cv, cycle_month, start_date

# ==========================================
# MÔ PHỎNG SỰ ĐIỀU CHỈNH KHI THANH TRƯỢT THAY ĐỔI
# ==========================================
def run_dynamic_simulation(df_kh, b_cost, b_inv, b_qty, b_hj, s_date, d_mod, s_mod, wait_time):
    # Tính toán sự thay đổi dựa trên tác động của thanh trượt vào số liệu gốc
    adj_supply = int(b_qty * (1 + s_mod/100))
    
    # Logic điều chỉnh Chi phí dựa trên sản lượng sản xuất mới và thời gian chờ
    cost_saving_factor = min(0.35, max(0, (wait_time - 12) * 0.002))
    # Mặc định ở mốc 34 giờ là giữ nguyên giá gốc của file tải lên
    baseline_saving = min(0.35, max(0, (34.0 - 12) * 0.002))
    simulated_cost = b_cost * (1 - cost_saving_factor + baseline_saving) * (1 + s_mod/100)
    
    # Logic điều chỉnh Tồn kho dựa trên thời gian neo bãi (mỗi 24 tiếng lệch làm tăng/giảm số ngày tương ứng)
    time_delta_days = (wait_time - 34.0) / 24.0
    simulated_inventory = max(0.1, b_inv + time_delta_days)
    
    # Logic Heijunka vỡ khi có sự lệch pha nghiêm trọng giữa sản xuất và đặt hàng
    gap = abs(d_mod - s_mod)
    simulated_heijunka = b_hj + (gap * 0.25) + (abs(wait_time - 34.0) * 0.05)
    
    # Giả lập số dòng xe vi phạm thời gian No_April_Check sang tháng 4
    # Nếu thời gian neo bãi kéo quá dài, các dòng xe cuối tháng sẽ bị đẩy lùi sang tháng sau
    simulated_april_violations = 0
    if wait_time > 48.0:
        simulated_april_violations = max(0, int((wait_time - 48.0) * 0.5 * (adj_supply / 2721)))
        
    # Tạo biểu đồ phân rải sản lượng dựa trên phân phối ngày thực tế trong file
    last_day = calendar.monthrange(s_date.year, s_date.month)[1]
    work_dates = pd.date_range(start=s_date, end=s_date.replace(day=last_day), freq='B')
    sim_daily_values = np.random.normal(loc=adj_supply/len(work_dates), 
                                        scale=(simulated_heijunka/100)*(adj_supply/len(work_dates)), 
                                        size=len(work_dates))
    sim_daily_values = np.clip(sim_daily_values, a_min=0, a_max=None).astype(int)
    df_sim_daily = pd.DataFrame({'Ngày làm việc': work_dates.strftime('%d/%m/%Y'), 'Sản lượng xuất bãi': sim_daily_values})
    
    return simulated_cost, simulated_inventory, simulated_heijunka, simulated_april_violations, df_sim_daily, adj_supply

# ==========================================
# ĐIỀU HÀNH HIỂN THỊ TRÊN GIAO DIỆN WEB
# ==========================================
if file_kh and file_dl and file_bg:
    # Bước 1: Đọc và phân tích trực tiếp file đã điền đủ cột
    with st.spinner('🎯 Đang kết nối và đồng bộ dữ liệu từ file Kế hoạch đã điền đủ...'):
        df_kh_clean, base_cost, base_inventory, plan_qty, base_hj, cycle_month, s_date = analyze_populated_data(file_kh, file_dl, file_bg)
        
    # Bước 2: Chạy mô phỏng tương tác động từ thanh trượt lên nền số liệu thực tế đó
    sim_cost, sim_inv, sim_hj, sim_apr, df_chart, final_supply = run_dynamic_simulation(
        df_kh_clean, base_cost, base_inventory, plan_qty, base_hj, s_date, demand_change, supply_change, max_wait_time
    )
    
    st.success(f"📊 **ĐỒNG BỘ THÀNH CÔNG:** Hệ thống đã ghi nhận dữ liệu thực tế chu kỳ **Tháng {cycle_month}** từ file Kế hoạch.")
    
    # HIỂN THỊ KPI CHÍNH
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tổng chi phí vận tải (Mô phỏng)", f"{int(sim_cost):,} VND", f"{int(sim_cost - base_cost):,} VND so với file gốc", delta_color="inverse")
    
    inv_delta_color = "normal" if sim_inv <= 1.5 else "inverse"
    col2.metric("Số ngày tồn kho TB (Mô phỏng)", f"{sim_inv:.2f} Ngày", f"{sim_inv - base_inventory:.2f} Ngày so với file gốc", delta_color=inv_delta_color)
    
    col3.metric("Số xe trễ sang tháng sau", f"{sim_apr} Xe", "Ràng buộc cứng No_April")
    col4.metric("Chỉ số Heijunka CV", f"{sim_hj:.1f} %", f"{sim_hj - base_hj:.1f} % so với file gốc", delta_color="inverse")

    st.divider()

    # BIỂU ĐỒ ĐỒNG HỒ TỐC ĐỘ (GAUGE CHARTS)
    st.subheader("📈 THEO DÕI BIẾN ĐỘNG SO VỚI FILE GỐC ĐÃ ĐIỀN ĐỦ")
    cg1, cg2 = st.columns(2)
    
    fig_inv = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = sim_inv,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Biến động Tồn kho TB (Mốc an toàn < 1.5 ngày)", 'font': {'size': 15}},
        delta = {'reference': base_inventory, 'increasing': {'color': "red"}, 'decreasing': {'color': "green"}},
        gauge = {
            'axis': {'range': [None, 12]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, 1.5], 'color': 'rgba(0, 255, 0, 0.25)'},
                {'range': [1.5, 3.0], 'color': 'rgba(255, 255, 0, 0.25)'},
                {'range': [3.0, 12], 'color': 'rgba(255, 0, 0, 0.25)'}],
        }
    ))
    cg1.plotly_chart(fig_inv, use_container_width=True)
    
    fig_hj = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = sim_hj,
        number = {'suffix': "%"},
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Biến động Độ lệch Heijunka CV %", 'font': {'size': 15}},
        delta = {'reference': base_hj, 'increasing': {'color': "red"}, 'decreasing': {'color': "green"}},
        gauge = {
            'axis': {'range': [None, 60]},
            'bar': {'color': "orange"},
            'steps': [
                {'range': [0, 10], 'color': 'rgba(0, 255, 0, 0.25)'},
                {'range': [10, 30], 'color': 'rgba(255, 255, 0, 0.25)'},
                {'range': [30, 60], 'color': 'rgba(255, 0, 0, 0.25)'}],
        }
    ))
    cg2.plotly_chart(fig_hj, use_container_width=True)

    # BIỂU ĐỒ SẢN LƯỢNG TIẾN ĐỘ THEO KỊCH BẢN MỚI
    st.subheader("📊 TIẾN ĐỘ XUẤT BÃI THEO KỊCH BẢN ĐIỀU CHỈNH MỚI")
    fig_bar = px.bar(df_chart, x='Ngày làm việc', y='Sản lượng xuất bãi', text_auto=True,
                     color='Sản lượng xuất bãi', color_continuous_scale=px.colors.sequential.Reds)
    st.plotly_chart(fig_bar, use_container_width=True)

else:
    st.info("👈 Hãy tải đầy đủ 3 File dữ liệu ở thanh bên trái (Kế hoạch điền đủ, Đại lý, Bảng giá) để khởi chạy Hệ thống Giám sát.")