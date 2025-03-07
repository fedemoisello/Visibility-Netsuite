import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime
import io
import json
import re
from datetime import datetime, timedelta

# Función para comparar versiones de datos
def compare_versions(current_df, previous_df):
    """
    Compara dos DataFrames de NetSuite y genera un resumen de cambios.
    
    Args:
    current_df (pd.DataFrame): DataFrame de la versión actual
    previous_df (pd.DataFrame): DataFrame de la versión anterior
    
    Returns:
    dict: Resumen de cambios
    """
    # Preparar datos para comparación
    def prepare_comparison_data(df):
        # Agrupar por cliente y calcular totales
        return df.groupby('Client')['Amount'].sum()
    
    current_totals = prepare_comparison_data(current_df)
    previous_totals = prepare_comparison_data(previous_df)
    
    # Calcular cambios
    changes = {}
    all_clients = set(current_totals.index) | set(previous_totals.index)
    
    for client in all_clients:
        current_amount = current_totals.get(client, 0)
        previous_amount = previous_totals.get(client, 0)
        
        # Calcular cambio absoluto y porcentual
        change_amount = current_amount - previous_amount
        change_percent = (change_amount / previous_amount * 100) if previous_amount != 0 else float('inf')
        
        changes[client] = {
            'current_amount': current_amount,
            'previous_amount': previous_amount,
            'change_amount': change_amount,
            'change_percent': change_percent
        }
    
    # Resumen general
    summary = {
        'total_current': current_totals.sum(),
        'total_previous': previous_totals.sum(),
        'total_change_amount': current_totals.sum() - previous_totals.sum(),
        'total_change_percent': ((current_totals.sum() - previous_totals.sum()) / previous_totals.sum() * 100) if previous_totals.sum() != 0 else float('inf')
    }
    
    return {
        'client_changes': changes,
        'summary': summary
    }

# Función para generar la tabla de reporte
def generate_report(netsuite_df):
    if netsuite_df is None or len(netsuite_df) == 0:
        return None
    
    # Crear pivot table
    pivot_table = pd.pivot_table(
        netsuite_df,
        values='Amount',
        index='Client',
        columns=['Trimestre', 'Mes_Nombre'],
        aggfunc='sum',
        fill_value=0
    )
    
    # Definir el orden correcto de los meses
    month_order = ['January', 'February', 'March', 'April', 'May', 'June', 
                  'July', 'August', 'September', 'October', 'November', 'December']
    
    # Reordenar las columnas manteniendo la jerarquía de trimestres
    # Primero, ordenar los trimestres
    quarter_order = ['Q1', 'Q2', 'Q3', 'Q4']
    quarter_cols = [q for q in quarter_order if q in pivot_table.columns.levels[0]]
    
    # Crear la lista de columnas ordenadas para meses por trimestre
    new_cols = []
    for q in quarter_cols:
        # Obtener los meses presentes en este trimestre
        q_months = [m for m in pivot_table[q].columns if m != 'Total']
        # Ordenar los meses según el orden natural
        q_months_ordered = sorted(q_months, key=lambda x: month_order.index(x) if x in month_order else 999)
        # Añadir las columnas ordenadas
        for m in q_months_ordered:
            new_cols.append((q, m))
            
    # Columnas para los totales trimestrales bajo 'Total'
    total_quarter_cols = []
    
    # Para almacenar totales de trimestres
    quarter_totals = {}
    # Calculamos los totales por trimestre, pero los colocamos bajo 'Total'
    for quarter in quarter_cols:
        # Obtener los meses presentes en este trimestre
        quarter_months = [m for m in pivot_table[quarter].columns if m != 'Total']
        if quarter_months:
            # Calcular el total para este trimestre
            pivot_table[('Total', quarter)] = pivot_table[quarter][quarter_months].sum(axis=1)
            # Guardar para el cálculo del total anual si es necesario
            quarter_totals[quarter] = pivot_table[('Total', quarter)]
            # Añadir a la lista de columnas de totales trimestrales
            total_quarter_cols.append(('Total', quarter))
    
    # Total anual - sumando todos los meses (sin contar los totales)
    monthly_cols = [(q, m) for q, m in new_cols]
    pivot_table[('Total', 'Anual')] = pivot_table[monthly_cols].sum(axis=1)
    
    # Ordenar clientes por total anual (descendente)
    pivot_table = pivot_table.sort_values(('Total', 'Anual'), ascending=False)
    
    # Orden final de columnas: primero trimestres con meses, luego totales de trimestre, finalmente total anual
    final_cols = new_cols + total_quarter_cols + [('Total', 'Anual')]
    
    # Reordenar las columnas del pivote
    if final_cols:
        pivot_table = pivot_table[final_cols]
    
    # Agregar fila de totales
    pivot_table.loc['Total'] = pivot_table.sum()
    
    return pivot_table

# Función para formatear valores en miles
def format_miles(x):
    if pd.isna(x) or x == 0:
        return ""
    return f"{int(round(x/1000))}K"

# Configuración de la página
st.set_page_config(layout="wide", page_title="Dashboard Visibility NetSuite", page_icon="📊")

# Definimos los goals anuales
PARTNER_GOALS = {
    "Laura Roubakhine": 1000000,  # 1MM USD
    # Agregar otros partners según sea necesario
}

# Función para normalizar nombres (eliminar espacios, convertir a minúscula)
def normalize_name(name):
    if not isinstance(name, str):
        return ""
    # Eliminar espacios adicionales y convertir a minúsculas
    normalized = name.strip().lower()
    # Normalizar formato "Apellido, Nombre" a "Nombre Apellido"
    if "," in normalized:
        parts = normalized.split(",")
        if len(parts) == 2:
            normalized = f"{parts[1].strip()} {parts[0].strip()}"
    return normalized

# Estilos personalizados
st.markdown("""
<style>
    .main-header {
        font-size: 26px;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 20px;
    }
    .sub-header {
        font-size: 20px;
        font-weight: bold;
        color: #34495e;
        margin-top: 30px;
        margin-bottom: 10px;
    }
    .metric-card {
        background-color: #f7f7f7;
        border-radius: 5px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #3498db;
    }
    .metric-title {
        font-size: 14px;
        color: #7f8c8d;
    }
    .highlighted {
        background-color: #e8f4f8;
    }
    .st-emotion-cache-1wivap2 {
        max-height: 600px;
        overflow-y: auto;
    }
    .caption {
        font-size: 12px;
        color: #7f8c8d;
        font-style: italic;
        margin-top: 5px;
    }
    .source-tag {
        font-size: 10px;
        font-weight: bold;
        padding: 2px 5px;
        border-radius: 3px;
        color: white;
    }
    .source-netsuite {
        background-color: #3498db;
    }
    .warning {
        color: #e74c3c;
        font-weight: bold;
    }
    .success {
        color: #2ecc71;
        font-weight: bold;
    }
    .progress-container {
        margin: 20px 0;
        padding: 15px;
        background-color: #f8f9fa;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .progress-title {
        font-size: 18px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .progress-subtitle {
        font-size: 14px;
        color: #666;
        margin-bottom: 15px;
    }
    .progress-stat {
        font-size: 16px;
        margin: 10px 0;
    }
    .goal-reached {
        color: #2ecc71;
    }
    .goal-pending {
        color: #e67e22;
    }
    .tab-content {
        padding: 20px 0;
    }
</style>
""", unsafe_allow_html=True)

# Título principal
st.markdown('<div class="main-header">Dashboard de Confirmado en NetSuite</div>', unsafe_allow_html=True)
st.markdown("Visualización de datos confirmados de NetSuite para análisis de ingresos.")

# Inicializar variables de sesión
if 'netsuite_data' not in st.session_state:
    st.session_state.netsuite_data = None
if 'previous_netsuite_data' not in st.session_state:
    st.session_state.previous_netsuite_data = None

# Función para procesar el CSV de NetSuite
@st.cache_data
def process_netsuite_csv(file_content, delimiter=';', encoding='utf-8'):
    try:
        # Intentar decodificar con la codificación especificada
        df = pd.read_csv(io.StringIO(file_content.decode(encoding)), delimiter=delimiter)
        
        # Intentar detectar la columna de fecha
        date_columns = [col for col in df.columns if 'date' in col.lower() or 'fecha' in col.lower()]
        date_col = date_columns[0] if date_columns else 'Date'
        
        # Intentar detectar la columna de cliente
        client_columns = [col for col in df.columns if 'client' in col.lower() or 'customer' in col.lower() or 'parent' in col.lower()]
        client_col = client_columns[0] if client_columns else 'Customer Parent'
        
        # Detectar columna de Partner (Client Leader AUX)
        partner_columns = [col for col in df.columns 
                          if 'client leader' in col.lower() 
                          or 'leader aux' in col.lower() 
                          or 'partner' in col.lower()]
        partner_col = partner_columns[0] if partner_columns else None
        
        # Si no se detectó automáticamente, permitir selección manual
        if not partner_col:
            partner_col = st.selectbox("Columna de Partner (Client Leader):", df.columns.tolist())
        
        # Detectar columna de PM
        pm_columns = [col for col in df.columns if 'pm' in col.lower()]
        pm_col = pm_columns[0] if pm_columns else None
        
        # Si no se detectó automáticamente, permitir selección manual
        if not pm_col:
            pm_col = st.selectbox("Columna de PM:", df.columns.tolist())
        
        # Forzar la columna de monto a "Total USD" específicamente
        amount_col = 'Total USD'
        
        # Verificar si la columna existe
        if amount_col not in df.columns:
            # Buscar alternativas si no existe
            amount_columns = [col for col in df.columns if 'usd' in col.lower() or 'total' in col.lower() or 'amount' in col.lower()]
            amount_col = amount_columns[0] if amount_columns else 'Total'
        
        # Convertir fechas
        try:
            df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
        except:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            except:
                pass
        
        # Convertir montos (considerando formato europeo con comas)
        if df[amount_col].dtype == object:  # Si es string
            df[amount_col] = df[amount_col].astype(str).str.replace('.', '').str.replace(',', '.').str.replace(' ', '')
            df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
        
        # Crear columnas de fecha
        if pd.api.types.is_datetime64_dtype(df[date_col]):
            df['Año'] = df[date_col].dt.year
            df['Mes'] = df[date_col].dt.month
            df['Mes_Nombre'] = df[date_col].dt.month_name()
            # Manejo seguro de valores NA o infinitos al crear la columna de trimestre
            df['Trimestre'] = 'Q' + df[date_col].dt.quarter.fillna(0).astype(int).astype(str)
            # Reemplazar Q0 (valores que eran NA) con un valor predeterminado
            df['Trimestre'] = df['Trimestre'].replace('Q0', 'Sin Trimestre')
            
            # Columna de mes formateada
            month_map = {
                1: 'Jan.', 2: 'Feb.', 3: 'Mar.', 4: 'Apr.', 
                5: 'May.', 6: 'Jun.', 7: 'Jul.', 8: 'Aug.',
                9: 'Sep.', 10: 'Oct.', 11: 'Nov.', 12: 'Dec.'
            }
            df['Month'] = df['Mes'].map(month_map) + ' ' + df['Año'].astype(str)
        
        # Agregar columna de origen
        df['Source'] = 'NetSuite'
        
        # Renombrar columnas para consistencia
        df = df.rename(columns={
            client_col: 'Client',
            amount_col: 'Amount',
            date_col: 'Date'
        })
        
        if partner_col:
            df = df.rename(columns={partner_col: 'Partner'})
        
        if pm_col:
            df = df.rename(columns={pm_col: 'PM'})
        
        # Asegurar que todos los valores categóricos sean string
        df['Client'] = df['Client'].astype(str)
        
        # Manejar columnas de Partner y PM si existen
        if 'Partner' in df.columns:
            df['Partner'] = df['Partner'].fillna('Sin asignar').astype(str)
            # Agregar columna normalizada para búsquedas
            df['Partner_Normalized'] = df['Partner'].apply(normalize_name)
        else:
            df['Partner'] = 'Sin asignar'
            df['Partner_Normalized'] = 'sin asignar'
            
        if 'PM' in df.columns:
            df['PM'] = df['PM'].fillna('Sin asignar').astype(str)
        else:
            df['PM'] = 'Sin asignar'
        
        return df
    except Exception as e:
        st.error(f"Error al procesar el CSV de NetSuite: {str(e)}")
        return None

# Interfaz: Sección de carga de archivos
with st.expander("🗂️ Carga de Datos", expanded=True):
    st.markdown("### Datos confirmados de NetSuite")
    netsuite_file = st.file_uploader("Carga tu archivo CSV de NetSuite", type=['csv'])
    
    # Opciones de delimitador y codificación
    delimiter_options = [';', ',', '\t', '|']
    encoding_options = ['utf-8', 'cp1252', 'latin1', 'iso-8859-1']
    
    if netsuite_file is not None:
        ns_delimiter = st.selectbox("Selecciona el delimitador", delimiter_options, index=0)
        ns_encoding = st.selectbox("Selecciona la codificación del archivo", encoding_options, index=0)
        
        if st.button("Procesar archivo de NetSuite"):
            file_content = netsuite_file.read()
            st.session_state.netsuite_data = process_netsuite_csv(file_content, delimiter=ns_delimiter, encoding=ns_encoding)
            
            if st.session_state.netsuite_data is not None:
                st.success(f"Archivo de NetSuite cargado correctamente: {netsuite_file.name}")
                st.markdown(f"**Registros procesados:** {len(st.session_state.netsuite_data)}")
                st.markdown(f"**Clientes únicos:** {st.session_state.netsuite_data['Client'].nunique()}")
                
                # Reemplazar expander anidado con un botón de expansión
                if st.button("Ver datos NetSuite (primeros 5 registros)"):
                    st.dataframe(st.session_state.netsuite_data.head())
    
    # Sección para cargar versión anterior
    st.markdown("### Versión Anterior del Reporte")
    previous_netsuite_file = st.file_uploader("Carga tu archivo CSV anterior de NetSuite", type=['csv'], key="previous_netsuite")
    
    if previous_netsuite_file is not None:
        previous_delimiter = st.selectbox("Selecciona el delimitador para el archivo anterior", delimiter_options, index=0, key="previous_delimiter")
        previous_encoding = st.selectbox("Selecciona la codificación del archivo anterior", encoding_options, index=0, key="previous_encoding")
        
        if st.button("Procesar archivo anterior de NetSuite"):
            previous_file_content = previous_netsuite_file.read()
            st.session_state.previous_netsuite_data = process_netsuite_csv(previous_file_content, delimiter=previous_delimiter, encoding=previous_encoding)
            
            if st.session_state.previous_netsuite_data is not None:
                st.success(f"Archivo anterior de NetSuite cargado correctamente: {previous_netsuite_file.name}")
                st.markdown(f"**Registros procesados:** {len(st.session_state.previous_netsuite_data)}")
                st.markdown(f"**Clientes únicos:** {st.session_state.previous_netsuite_data['Client'].nunique()}")

# Si los datos están listos, mostrar el dashboard con tabs
if st.session_state.netsuite_data is not None:
    # Tabs para organizar el dashboard (agregamos un quinto tab para comparación)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📈 Visualizaciones", "🎯 Seguimiento de Goals", "🔄 Comparación de Versiones", "⚙️ Configuración"])
    
    with tab1:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Configuración del Dashboard</div>', unsafe_allow_html=True)
        
        # Filtros
        st.markdown("### Filtros")
        
        # Primera fila de filtros (Cliente, Año, Trimestre)
        col1, col2, col3 = st.columns(3)
        
        all_clients = set()
        all_clients.update(st.session_state.netsuite_data['Client'].astype(str).unique())
        
        with col1:
            selected_clients = st.multiselect(
                "Clientes", 
                sorted(all_clients),
                default=[]
            )
        
        with col2:
            year_options = st.session_state.netsuite_data['Año'].dropna().unique().astype(int).astype(str).tolist()
            year_options = sorted(set(year_options))
            
            if year_options:
                selected_year = st.selectbox("Año", ["Todos"] + year_options, index=0)
            else:
                selected_year = "Todos"
        
        with col3:
            selected_quarter = st.selectbox("Trimestre", ["Todos", "Q1", "Q2", "Q3", "Q4"], index=0)
        
        # Segunda fila de filtros (Partner, PM)
        col4, col5, col6 = st.columns(3)
        
        # Obtener valores únicos para Partner y PM
        all_partners = set()
        all_pms = set()
        all_partners.update(st.session_state.netsuite_data['Partner'].astype(str).unique())
        all_pms.update(st.session_state.netsuite_data['PM'].astype(str).unique())
        
        with col4:
            selected_partners = st.multiselect(
                "Partner", 
                sorted(all_partners),
                default=[]
            )
        
        with col5:
            selected_pms = st.multiselect(
                "PM", 
                sorted(all_pms),
                default=[]
            )
        
        # Aplicar filtros a NetSuite
        filtered_netsuite = st.session_state.netsuite_data.copy()
        
        if selected_clients:
            filtered_netsuite = filtered_netsuite[filtered_netsuite['Client'].astype(str).isin(selected_clients)]
        
        if selected_year != "Todos":
            filtered_netsuite = filtered_netsuite[filtered_netsuite['Año'] == int(selected_year)]
        
        if selected_quarter != "Todos":
            filtered_netsuite = filtered_netsuite[filtered_netsuite['Trimestre'] == selected_quarter]
            
        # Aplicar los nuevos filtros
        if selected_partners:
            filtered_netsuite = filtered_netsuite[filtered_netsuite['Partner'].astype(str).isin(selected_partners)]
            
        if selected_pms:
            filtered_netsuite = filtered_netsuite[filtered_netsuite['PM'].astype(str).isin(selected_pms)]
        
        # Generar el reporte con los datos filtrados
        report_table = generate_report(filtered_netsuite)
        
        if report_table is not None:
            st.markdown('<div class="sub-header">Reporte de Visibility NetSuite</div>', unsafe_allow_html=True)
            
            # Mostrar leyenda
            st.markdown("""
            <div style="display: flex; margin-bottom: 10px;">
                <div><span class="source-tag source-netsuite">NS</span> NetSuite (Confirmados)</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Formatear tabla para mostrar en miles (K)
            formatted_table = report_table.applymap(format_miles)
            
            # Mostrar la tabla
            st.dataframe(formatted_table, use_container_width=True)
            
            # Opción para descargar la tabla
            csv_buffer = io.StringIO()
            report_table.to_csv(csv_buffer)
            csv_string = csv_buffer.getvalue()
            
            st.download_button(
                label="Descargar reporte como CSV",
                data=csv_string,
                file_name=f"reporte_visibility_netsuite_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
        else:
            st.warning("No hay datos para mostrar con los filtros seleccionados.")
        st.markdown('</div>', unsafe_allow_html=True)

# NOTA: Este es un fragmento parcial del código. Continúa con los demás tabs (tab2, tab3, tab4, tab5) en el siguiente artifact.

    with tab2:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Visualizaciones</div>', unsafe_allow_html=True)
        
        # Preparar datos para visualizaciones
        visualization_data = filtered_netsuite.copy()
        
        # Gráfico 1: Distribución por cliente (Top 20)
        if not visualization_data.empty:
            client_data = visualization_data.groupby('Client')['Amount'].sum().reset_index()
            
            fig1 = px.bar(
                client_data.sort_values('Amount', ascending=False).head(20),
                x='Client',
                y='Amount',
                title=f"Distribución de ingresos por cliente (Top 20)",
                color_discrete_sequence=['#3498db'],
                labels={'Amount': 'Monto USD', 'Client': 'Cliente'}
            )
            
            st.plotly_chart(fig1, use_container_width=True)
            
            # Gráfico 2: Tendencia mensual
            monthly_data = visualization_data.groupby(['Año', 'Mes', 'Mes_Nombre'])['Amount'].sum().reset_index()
            
            # Crear fechas correctamente usando el constructor de datetime
            monthly_data['Fecha'] = monthly_data.apply(
                lambda row: datetime(
                    year=int(row['Año']), 
                    month=int(row['Mes']), 
                    day=1
                ), axis=1
            )
            
            monthly_data = monthly_data.sort_values('Fecha')
            
            # Definimos un orden personalizado para los meses
            month_order = ['January', 'February', 'March', 'April', 'May', 'June', 
                          'July', 'August', 'September', 'October', 'November', 'December']
            
            fig2 = px.bar(
                monthly_data,
                x='Mes_Nombre',
                y='Amount',
                text=monthly_data['Amount'].apply(lambda x: f"${x/1000:.0f}K"),
                title="Tendencia mensual de ingresos",
                color_discrete_sequence=['#3498db'],
                labels={'Amount': 'Monto USD', 'Mes_Nombre': 'Mes'}
            )
            
            # Aplicamos el orden a la gráfica de tendencia mensual
            fig2.update_xaxes(categoryorder='array', categoryarray=month_order)
            
            st.plotly_chart(fig2, use_container_width=True)
            
            # Gráfico 3: Comparativo trimestral
            quarterly_data = visualization_data.groupby('Trimestre')['Amount'].sum().reset_index()
            
            fig3 = px.bar(
                quarterly_data,
                x='Trimestre',
                y='Amount',
                text=quarterly_data['Amount'].apply(lambda x: f"${x/1000:.0f}K"),
                title="Comparativo trimestral",
                color_discrete_sequence=['#3498db'],
                labels={'Amount': 'Monto USD', 'Trimestre': 'Trimestre'}
            )
            
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.warning("No hay datos para mostrar con los filtros seleccionados.")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab3:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Seguimiento de Goals Anuales 2025</div>', unsafe_allow_html=True)
        
        # Año fijo para el seguimiento
        goal_year = "2025"
        
        # Filtrar datos solo para ese año (aunque no haya datos aún, preparamos la estructura)
        year_data = st.session_state.netsuite_data.copy()
        year_data = year_data[year_data['Año'] == int(goal_year)] if 'Año' in year_data.columns else pd.DataFrame()
        
        # Variables para el partner específico
        partner_name = "Laura Roubakhine"
        partner_normalized = normalize_name(partner_name)
        partner_goal = PARTNER_GOALS[partner_name]  # 1MM USD
        
        # Calcular datos reales - usando normalización de nombres para mayor robustez
        if not year_data.empty and 'Partner_Normalized' in year_data.columns:
            # Buscar registros que coincidan con el partner normalizado
            matching_partners = [p for p in year_data['Partner_Normalized'].unique() 
                                if partner_normalized in p or 
                                p in partner_normalized or
                                "roubakhine" in p or
                                "laura" in p]
            
            if matching_partners:
                partner_data = year_data[year_data['Partner_Normalized'].isin(matching_partners)]
                partner_total = partner_data['Amount'].sum() if not partner_data.empty else 0
            else:
                # Si no hay coincidencias, usar datos de ejemplo
                partner_total = 350000  # Ejemplo: $350,000 USD (35% de progreso)
        else:
            # Si no hay datos, usamos datos de ejemplo para mostrar la funcionalidad
            partner_total = 350000  # Ejemplo: $350,000 USD (35% de progreso)
            
        # Calcular porcentaje de progreso
        progress_percentage = min(100, (partner_total / partner_goal) * 100)
        
        # Mostrar encabezado de progreso
        st.markdown('<div class="progress-container">', unsafe_allow_html=True)
        st.markdown(f'<div class="progress-title">Meta Anual {goal_year} - {partner_name}</div>', unsafe_allow_html=True)
        
        # Mostrar progreso en barra horizontal
        st.progress(progress_percentage / 100)
        
        # Mostrar información detallada
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f'<div class="progress-stat">Meta Anual: <strong>${partner_goal:,.2f}</strong></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="progress-stat">Acumulado: <strong>${partner_total:,.2f}</strong></div>', unsafe_allow_html=True)
        with col3:
            status_class = "goal-reached" if progress_percentage >= 100 else "goal-pending"
            st.markdown(f'<div class="progress-stat">Progreso: <strong class="{status_class}">{progress_percentage:.1f}%</strong></div>', unsafe_allow_html=True)
        
        # Agregar información de faltante y predicción
        col1, col2 = st.columns(2)
        with col1:
            remaining = partner_goal - partner_total
            st.markdown(f'<div class="progress-stat">Faltante: <strong>${remaining:,.2f}</strong></div>', unsafe_allow_html=True)
        with col2:
            # Calcular mes actual
            current_month = datetime.now().month
            months_remaining = 12 - current_month
            if months_remaining > 0:
                monthly_target = remaining / months_remaining
                st.markdown(f'<div class="progress-stat">Meta mensual para alcanzar objetivo: <strong>${monthly_target:,.2f}</strong></div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Si hay datos reales, mostrar distribución por cliente
        if partner_total > 0 and partner_total != 350000 and not year_data.empty:
            if 'Partner_Normalized' in year_data.columns and matching_partners:
                partner_data = year_data[year_data['Partner_Normalized'].isin(matching_partners)]
                if not partner_data.empty:
                    client_data = partner_data.groupby('Client')['Amount'].sum().reset_index()
                    
                    # Gráfico de distribución por cliente
                    fig = px.pie(
                        client_data,
                        values='Amount',
                        names='Client',
                        title=f"Distribución por cliente para {partner_name} en {goal_year}",
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Tabla de clientes
                    client_data = client_data.sort_values('Amount', ascending=False)
                    client_data['Porcentaje'] = client_data['Amount'] / client_data['Amount'].sum() * 100
                    client_data['Amount'] = client_data['Amount'].apply(lambda x: f"${x:,.2f}")
                    client_data['Porcentaje'] = client_data['Porcentaje'].apply(lambda x: f"{x:.1f}%")
                    
                    st.dataframe(client_data, use_container_width=True)
        else:
            # Mostrar mensaje explicativo
            st.info(f"El seguimiento muestra el progreso hacia la meta anual de ${partner_goal:,.2f} para {partner_name} en {goal_year}. " 
                    f"Actualmente se ha alcanzado un {progress_percentage:.1f}% del objetivo.")
            
            st.markdown("### Recomendaciones")
            st.markdown("""
            - Revisar oportunidades de nuevos proyectos con clientes existentes
            - Realizar seguimiento de oportunidades en pipeline
            - Considerar estrategias para aumentar el valor de los proyectos actuales
            """)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab4:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Comparación de Versiones</div>', unsafe_allow_html=True)
        
        # Verificar si hay una versión anterior cargada
        if hasattr(st.session_state, 'previous_netsuite_data') and st.session_state.previous_netsuite_data is not None:
            # Realizar comparación
            version_comparison = compare_versions(st.session_state.netsuite_data, st.session_state.previous_netsuite_data)
            
            # Mostrar resumen general
            summary = version_comparison['summary']
            st.markdown("### Resumen General de Cambios")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Versión Actual", f"${summary['total_current']:,.2f}")
            with col2:
                st.metric("Total Versión Anterior", f"${summary['total_previous']:,.2f}")
            with col3:
                delta_color = "normal" if summary['total_change_amount'] > 0 else "inverse"
                st.metric("Cambio Total", 
                          f"${summary['total_change_amount']:,.2f}", 
                          f"{summary['total_change_percent']:.2f}%",
                          delta_color=delta_color)
            
            # Tabla de cambios por cliente
            st.markdown("### Cambios por Cliente")
            changes_data = []
            for client, change_info in version_comparison['client_changes'].items():
                changes_data.append({
                    'Cliente': client,
                    'Monto Actual': change_info['current_amount'],
                    'Monto Anterior': change_info['previous_amount'],
                    'Cambio Monto': change_info['change_amount'],
                    'Cambio %': change_info['change_percent']
                })
            
            # Convertir a DataFrame para mostrar
            changes_df = pd.DataFrame(changes_data)
            
            # Ordenar por cambio absoluto en valor absoluto
            changes_df['Cambio Absoluto'] = abs(changes_df['Cambio Monto'])
            changes_df = changes_df.sort_values('Cambio Absoluto', ascending=False)
            
            # Formatear columnas
            changes_df['Monto Actual'] = changes_df['Monto Actual'].apply(lambda x: f"${x:,.2f}")
            changes_df['Monto Anterior'] = changes_df['Monto Anterior'].apply(lambda x: f"${x:,.2f}")
            changes_df['Cambio Monto'] = changes_df['Cambio Monto'].apply(lambda x: f"${x:,.2f}")
            changes_df['Cambio %'] = changes_df['Cambio %'].apply(lambda x: f"{x:.2f}%")
            
            # Eliminar columna auxiliar
            changes_df = changes_df.drop(columns=['Cambio Absoluto'])
            
            # Mostrar tabla
            st.dataframe(changes_df, use_container_width=True)
            
            # Gráfico de cambios por cliente
            top_changes = changes_df.head(10)  # Top 10 cambios
            
            # Crear gráfico de barras para cambios por cliente
            fig_changes = px.bar(
                top_changes, 
                x='Cliente', 
                y='Cambio Monto',
                title="Top 10 Cambios por Cliente",
                labels={'Cambio Monto': 'Cambio en Monto USD', 'Cliente': 'Cliente'},
                color='Cambio Monto',
                color_continuous_scale=px.colors.diverging.RdYlGn
            )
            
            st.plotly_chart(fig_changes, use_container_width=True)
            
            # Función para comparar versiones por grupo
            def compare_versions_by_group(current_df, previous_df, group_column):
                """
                Compara dos DataFrames de NetSuite agrupando por una columna específica.
                """
                def prepare_comparison_data(df):
                    # Agrupar por la columna especificada y calcular totales
                    return df.groupby(group_column)['Amount'].sum()
                
                current_totals = prepare_comparison_data(current_df)
                previous_totals = prepare_comparison_data(previous_df)
                
                # Calcular cambios
                changes = {}
                all_groups = set(current_totals.index) | set(previous_totals.index)
                
                for group in all_groups:
                    current_amount = current_totals.get(group, 0)
                    previous_amount = previous_totals.get(group, 0)
                    
                    # Calcular cambio absoluto y porcentual
                    change_amount = current_amount - previous_amount
                    change_percent = (change_amount / previous_amount * 100) if previous_amount != 0 else float('inf')
                    
                    changes[group] = {
                        'current_amount': current_amount,
                        'previous_amount': previous_amount,
                        'change_amount': change_amount,
                        'change_percent': change_percent
                    }
                
                # Ordenar por cambio absoluto
                sorted_changes = sorted(
                    changes.items(), 
                    key=lambda x: abs(x[1]['change_amount']), 
                    reverse=True
                )
                
                return sorted_changes

            # Función para crear tabla de cambios
            def create_changes_dataframe(sorted_changes):
                """
                Crea un DataFrame a partir de los cambios ordenados.
                """
                changes_data = []
                for group, change_info in sorted_changes:
                    changes_data.append({
                        'Grupo': group,
                        'Monto Actual': change_info['current_amount'],
                        'Monto Anterior': change_info['previous_amount'],
                        'Cambio Monto': change_info['change_amount'],
                        'Cambio %': change_info['change_percent']
                    })
                
                # Convertir a DataFrame
                changes_df = pd.DataFrame(changes_data)
                
                # Formatear columnas
                changes_df['Monto Actual'] = changes_df['Monto Actual'].apply(lambda x: f"${x:,.2f}")
                changes_df['Monto Anterior'] = changes_df['Monto Anterior'].apply(lambda x: f"${x:,.2f}")
                changes_df['Cambio Monto'] = changes_df['Cambio Monto'].apply(lambda x: f"${x:,.2f}")
                changes_df['Cambio %'] = changes_df['Cambio %'].apply(lambda x: f"{x:.2f}%")
                
                return changes_df

            # Comparación por Project Code
            st.markdown("### Cambios por Código de Proyecto")
            try:
                # Verificar si la columna existe en ambos DataFrames
                project_columns = [col for col in ['_Prj Code', 'Project Code', 'Prj Code'] if col in st.session_state.netsuite_data.columns 
                                   and col in st.session_state.previous_netsuite_data.columns]
                
                if project_columns:
                    project_code_column = project_columns[0]
                    project_changes = compare_versions_by_group(
                        st.session_state.netsuite_data, 
                        st.session_state.previous_netsuite_data, 
                        project_code_column
                    )
                    
                    # Mostrar tabla de cambios por Project Code
                    project_changes_df = create_changes_dataframe(project_changes[:10])  # Top 10
                    st.dataframe(project_changes_df, use_container_width=True)
                    
                    # Gráfico de cambios por Project Code
                    fig_project = px.bar(
                        project_changes_df, 
                        x='Grupo', 
                        y='Cambio Monto',
                        title=f"Top 10 Cambios por {project_code_column}",
                        labels={'Cambio Monto': 'Cambio en Monto USD', 'Grupo': 'Código de Proyecto'},
                        color='Cambio Monto',
                        color_continuous_scale=px.colors.diverging.RdYlGn
                    )
                    st.plotly_chart(fig_project, use_container_width=True)
                else:
                    st.warning("No se encontró la columna de Código de Proyecto en los archivos.")
            except Exception as e:
                st.error(f"Error al procesar cambios por Código de Proyecto: {str(e)}")

            # Comparación por Client Leader AUX (Partner)
            with st.expander("Cambios por Client Leader AUX", expanded=False):
                st.markdown("### Cambios por Client Leader AUX")
                try:
                    # Verificar si la columna existe en ambos DataFrames
                    partner_columns = [col for col in ['_Client Leader AUX', 'Client Leader AUX', 'Partner'] if col in st.session_state.netsuite_data.columns 
                                       and col in st.session_state.previous_netsuite_data.columns]
                    
                    if partner_columns:
                        partner_column = partner_columns[0]
                        partner_changes = compare_versions_by_group(
                            st.session_state.netsuite_data, 
                            st.session_state.previous_netsuite_data, 
                            partner_column
                        )
                        
                        # Mostrar tabla de cambios por Partner
                        partner_changes_df = create_changes_dataframe(partner_changes[:10])  # Top 10
                        st.dataframe(partner_changes_df, use_container_width=True)
                        
                        # Gráfico de cambios por Partner
                        fig_partner = px.bar(
                            partner_changes_df, 
                            x='Grupo', 
                            y='Cambio Monto',
                            title=f"Top 10 Cambios por {partner_column}",
                            labels={'Cambio Monto': 'Cambio en Monto USD', 'Grupo': 'Client Leader AUX'},
                            color='Cambio Monto',
                            color_continuous_scale=px.colors.diverging.RdYlGn
                        )
                        st.plotly_chart(fig_partner, use_container_width=True)
                    else:
                        st.warning("No se encontró la columna de Client Leader AUX en los archivos.")
                except Exception as e:
                    st.error(f"Error al procesar cambios por Client Leader AUX: {str(e)}")

            # Comparación por PM
            with st.expander("### Cambios por PM", expanded=False):
                st.markdown("### Cambios por PM")
                try:
                    # Verificar si la columna existe en ambos DataFrames
                    pm_columns = [col for col in ['_PM', 'PM'] if col in st.session_state.netsuite_data.columns 
                                  and col in st.session_state.previous_netsuite_data.columns]
                
                    if pm_columns:
                        pm_column = pm_columns[0]
                        pm_changes = compare_versions_by_group(
                            st.session_state.netsuite_data, 
                            st.session_state.previous_netsuite_data, 
                            pm_column
                        )
                    
                        # Mostrar tabla de cambios por PM
                        pm_changes_df = create_changes_dataframe(pm_changes[:10])  # Top 10
                        st.dataframe(pm_changes_df, use_container_width=True)
                    
                        # Gráfico de cambios por PM
                        fig_pm = px.bar(
                            pm_changes_df, 
                            x='Grupo', 
                            y='Cambio Monto',
                            title=f"Top 10 Cambios por {pm_column}",
                            labels={'Cambio Monto': 'Cambio en Monto USD', 'Grupo': 'PM'},
                            color='Cambio Monto',
                            color_continuous_scale=px.colors.diverging.RdYlGn
                        )
                        st.plotly_chart(fig_pm, use_container_width=True)
                    else:
                        st.warning("No se encontró la columna de PM en los archivos.")
                except Exception as e:
                    st.error(f"Error al procesar cambios por PM: {str(e)}")

            # Comparación por Mes
            if hasattr(st.session_state, 'previous_netsuite_data'):
                st.markdown("### Cambios por Mes")
                try:
                    # Agrupar datos por mes
                    current_monthly = st.session_state.netsuite_data.groupby(['Año', 'Mes_Nombre'])['Amount'].sum().reset_index()
                    previous_monthly = st.session_state.previous_netsuite_data.groupby(['Año', 'Mes_Nombre'])['Amount'].sum().reset_index()
                    
                    # Crear diccionario de orden de meses
                    month_order_dict = {
                        'January': 1, 'February': 2, 'March': 3, 'April': 4, 
                        'May': 5, 'June': 6, 'July': 7, 'August': 8, 
                        'September': 9, 'October': 10, 'November': 11, 'December': 12
                    }
                    
                    # Crear un DataFrame para comparación
                    monthly_comparison = pd.merge(
                        current_monthly, 
                        previous_monthly, 
                        on='Mes_Nombre', 
                        suffixes=('_actual', '_anterior')
                    )
                    
                    # Agregar columna de orden
                    monthly_comparison['Mes_Orden'] = monthly_comparison['Mes_Nombre'].map(month_order_dict)
                    
                    # Calcular cambios
                    monthly_comparison['Cambio_Monto'] = monthly_comparison['Amount_actual'] - monthly_comparison['Amount_anterior']
                    monthly_comparison['Cambio_Porcentaje'] = (monthly_comparison['Cambio_Monto'] / monthly_comparison['Amount_anterior'] * 100)
                    
                    # Ordenar por orden de mes
                    monthly_comparison = monthly_comparison.sort_values('Mes_Orden')
                    
                    # Formatear para mostrar
                    monthly_comparison_display = monthly_comparison.copy()
                    monthly_comparison_display['Amount_actual'] = monthly_comparison_display['Amount_actual'].apply(lambda x: f"${x:,.2f}")
                    monthly_comparison_display['Amount_anterior'] = monthly_comparison_display['Amount_anterior'].apply(lambda x: f"${x:,.2f}")
                    monthly_comparison_display['Cambio_Monto'] = monthly_comparison_display['Cambio_Monto'].apply(lambda x: f"${x:,.2f}")
                    monthly_comparison_display['Cambio_Porcentaje'] = monthly_comparison_display['Cambio_Porcentaje'].apply(lambda x: f"{x:.2f}%")
                    
                    # Mostrar tabla
                    st.dataframe(monthly_comparison_display[['Mes_Nombre', 'Amount_anterior', 'Amount_actual', 'Cambio_Monto', 'Cambio_Porcentaje']], 
                                 use_container_width=True)
                    
                    # Gráfico de cambios por mes
                    fig_monthly = px.bar(
                        monthly_comparison, 
                        x='Mes_Nombre',
                        y='Cambio_Monto',
                        title="Cambios por Mes",
                        labels={'Cambio_Monto': 'Cambio en Monto USD', 'Mes_Nombre': 'Mes'},
                        color='Cambio_Monto',
                        color_continuous_scale=px.colors.diverging.RdYlGn,
                        category_orders={'Mes_Nombre': [
                            'January', 'February', 'March', 'April', 'May', 'June', 
                            'July', 'August', 'September', 'October', 'November', 'December'
                        ]}
                    )
                    
                    # Actualizar trazas para hover
                    fig_monthly.update_traces(
                        hovertemplate='<b>%{x}</b><br>Cambio: %{y:,.2f} USD<extra></extra>'
                    )
                    
                    st.plotly_chart(fig_monthly, use_container_width=True)
                    
                    # Selector de mes para detalles
                    selected_month = st.selectbox("Selecciona un mes para ver detalles detallados", monthly_comparison['Mes_Nombre'].tolist())
                    
                    # Función para obtener detalles del mes
                    def get_month_details(month):
                        # Filtrar datos del mes actual y anterior
                        current_month_data = st.session_state.netsuite_data[
                            st.session_state.netsuite_data['Mes_Nombre'] == month
                        ]
                        previous_month_data = st.session_state.previous_netsuite_data[
                            st.session_state.previous_netsuite_data['Mes_Nombre'] == month
                        ]
                        
                        # Pestañas para diferentes vistas
                        tab_clients, tab_projects = st.tabs(["Clientes", "Códigos de Proyecto"])
                        
                        with tab_clients:
                            # Agrupar por cliente
                            current_clients = current_month_data.groupby('Client')['Amount'].sum().reset_index()
                            previous_clients = previous_month_data.groupby('Client')['Amount'].sum().reset_index()
                            
                            # Merge de datos
                            client_comparison = pd.merge(
                                current_clients, 
                                previous_clients, 
                                on='Client', 
                                suffixes=('_actual', '_anterior')
                            )
                            
                            # Calcular cambios
                            client_comparison['Cambio_Monto'] = client_comparison['Amount_actual'] - client_comparison['Amount_anterior']
                            client_comparison['Cambio_Porcentaje'] = (client_comparison['Cambio_Monto'] / client_comparison['Amount_anterior'] * 100)
                            
                            # Ordenar por cambio absoluto
                            client_comparison = client_comparison.sort_values('Cambio_Monto', key=abs, ascending=False)
                            
                            # Formatear
                            client_comparison['Amount_actual'] = client_comparison['Amount_actual'].apply(lambda x: f"${x:,.2f}")
                            client_comparison['Amount_anterior'] = client_comparison['Amount_anterior'].apply(lambda x: f"${x:,.2f}")
                            client_comparison['Cambio_Monto'] = client_comparison['Cambio_Monto'].apply(lambda x: f"${x:,.2f}")
                            client_comparison['Cambio_Porcentaje'] = client_comparison['Cambio_Porcentaje'].apply(lambda x: f"{x:.2f}%")
                            
                            st.dataframe(client_comparison, use_container_width=True)
                        
                        with tab_projects:
                            # Agrupar por código de proyecto
                            current_projects = current_month_data.groupby('Prj Code')['Amount'].sum().reset_index()
                            previous_projects = previous_month_data.groupby('Prj Code')['Amount'].sum().reset_index()
                            
                            # Merge de datos
                            project_comparison = pd.merge(
                                current_projects, 
                                previous_projects, 
                                on='Prj Code', 
                                suffixes=('_actual', '_anterior')
                            )
                            
                            # Calcular cambios
                            project_comparison['Cambio_Monto'] = project_comparison['Amount_actual'] - project_comparison['Amount_anterior']
                            project_comparison['Cambio_Porcentaje'] = (project_comparison['Cambio_Monto'] / project_comparison['Amount_anterior'] * 100)
                            
                            # Ordenar por cambio absoluto
                            project_comparison = project_comparison.sort_values('Cambio_Monto', key=abs, ascending=False)
                            
                            # Formatear
                            project_comparison['Amount_actual'] = project_comparison['Amount_actual'].apply(lambda x: f"${x:,.2f}")
                            project_comparison['Amount_anterior'] = project_comparison['Amount_anterior'].apply(lambda x: f"${x:,.2f}")
                            project_comparison['Cambio_Monto'] = project_comparison['Cambio_Monto'].apply(lambda x: f"${x:,.2f}")
                            project_comparison['Cambio_Porcentaje'] = project_comparison['Cambio_Porcentaje'].apply(lambda x: f"{x:.2f}%")
                            
                            st.dataframe(project_comparison, use_container_width=True)
                    
                    # Llamar a la función con el mes seleccionado
                    get_month_details(selected_month)

                except Exception as e:
                    st.error(f"Error al procesar cambios por Mes: {str(e)}")
        
        else:
            st.info("Carga un archivo de versión anterior para realizar comparación.")
        
        st.markdown('</div>', unsafe_allow_html=True)

    with tab5:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Configuración del Dashboard</div>', unsafe_allow_html=True)
        
        st.markdown("### Opciones de visualización")
        
        st.markdown("Esta sección permite configurar las opciones del dashboard:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.checkbox("Mostrar montos en miles (K)", value=True)
            st.checkbox("Aplicar formato a tablas", value=True)
        
        with col2:
            st.checkbox("Mostrar totales por trimestre", value=True)
            st.checkbox("Mostrar totales anuales", value=True)
        
        st.markdown("### Goals anuales")
        
        # Mostrar los goals configurados
        st.markdown("Meta anual configurada:")
        st.markdown(f"- **Laura Roubakhine**: ${PARTNER_GOALS['Laura Roubakhine']:,.2f}")
        
        st.markdown("Para modificar este valor, contacta al administrador del sistema.")
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # Mensaje cuando no hay archivo cargado
    st.info("Carga el archivo de NetSuite para comenzar el análisis.")
    
    # Dashboard information placeholder
    st.markdown('<div class="sub-header">Información del Dashboard</div>', unsafe_allow_html=True)
    st.markdown("""
    Este dashboard de NetSuite te permite:
    
    1. **Cargar y visualizar datos confirmados** de NetSuite
    
    2. **Filtrar datos** por año, trimestre y cliente
    
    3. **Visualizar tendencias** con gráficos interactivos:
       - Distribución por cliente
       - Tendencia mensual
       - Comparativo trimestral
    
    4. **Exportar resultados** en formato CSV
    
    Sube tu archivo para comenzar.
    """)

# Footer
st.markdown("---")
st.markdown("Dashboard de Visibility NetSuite v1.1 | Desarrollado con Streamlit")
