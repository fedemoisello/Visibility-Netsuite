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

# Configuración de la página
st.set_page_config(layout="wide", page_title="Dashboard Visibility NetSuite", page_icon="📊")

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
</style>
""", unsafe_allow_html=True)

# Título principal
st.markdown('<div class="main-header">Dashboard de Visibility NetSuite</div>', unsafe_allow_html=True)
st.markdown("Visualización de datos confirmados de NetSuite para análisis de ingresos.")

# Inicializar variables de sesión
if 'netsuite_data' not in st.session_state:
    st.session_state.netsuite_data = None

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
        
        # Asegurar que Client siempre sea string
        df['Client'] = df['Client'].astype(str)
        
        return df
    except Exception as e:
        st.error(f"Error al procesar el CSV de NetSuite: {str(e)}")
        return None

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

# Interfaz: Sección de carga de archivos
st.markdown('<div class="sub-header">Carga de Datos</div>', unsafe_allow_html=True)

st.markdown("### Datos confirmados de NetSuite")
netsuite_file = st.file_uploader("Carga tu archivo CSV de NetSuite", type=['csv'])

if netsuite_file is not None:
    delimiter_options = [';', ',', '\t', '|']
    ns_delimiter = st.selectbox("Selecciona el delimitador", delimiter_options, index=0)
    
    encoding_options = ['utf-8', 'cp1252', 'latin1', 'iso-8859-1']
    ns_encoding = st.selectbox("Selecciona la codificación del archivo", encoding_options, index=0)
    
    if st.button("Procesar archivo de NetSuite"):
        file_content = netsuite_file.read()
        st.session_state.netsuite_data = process_netsuite_csv(file_content, delimiter=ns_delimiter, encoding=ns_encoding)
        
        if st.session_state.netsuite_data is not None:
            st.success(f"Archivo de NetSuite cargado correctamente: {netsuite_file.name}")
            st.markdown(f"**Registros procesados:** {len(st.session_state.netsuite_data)}")
            st.markdown(f"**Clientes únicos:** {st.session_state.netsuite_data['Client'].nunique()}")
            with st.expander("Ver datos NetSuite (primeros 5 registros)"):
                st.dataframe(st.session_state.netsuite_data.head())

# Si los datos están listos, mostrar el dashboard
if st.session_state.netsuite_data is not None:
    st.markdown('<div class="sub-header">Configuración del Dashboard</div>', unsafe_allow_html=True)
    
    # Filtros
    st.markdown("### Filtros")
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
    
    # Aplicar filtros a NetSuite
    filtered_netsuite = st.session_state.netsuite_data.copy()
    
    if selected_clients:
        filtered_netsuite = filtered_netsuite[filtered_netsuite['Client'].astype(str).isin(selected_clients)]
    
    if selected_year != "Todos":
        filtered_netsuite = filtered_netsuite[filtered_netsuite['Año'] == int(selected_year)]
    
    if selected_quarter != "Todos":
        filtered_netsuite = filtered_netsuite[filtered_netsuite['Trimestre'] == selected_quarter]
    
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
        
        # Visualizaciones
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

# Se eliminó la información adicional para optimizar el código

# Footer
st.markdown("---")
st.markdown("Dashboard de Visibility NetSuite v1.0 | Desarrollado con Streamlit")