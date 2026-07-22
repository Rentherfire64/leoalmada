import os
import sys
import sqlite3
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify

# Para el diseño del PDF (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    template_folder = 'templates'
    static_folder = 'static'

CARPETA_PDFS = os.path.join(BASE_DIR, 'presupuestos')
if not os.path.exists(CARPETA_PDFS):
    os.makedirs(CARPETA_PDFS)

DB_PATH = os.path.join(BASE_DIR, 'database.db')

app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)


# --- INICIALIZACIÓN Y PRECARGA DE DATOS DE PRUEBA ---
def inicializar_db():
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    
    # 1. Creación de Tablas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            contacto TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            precio REAL NOT NULL,
            precio_costo REAL DEFAULT 0.0,
            porcentaje_ganancia REAL DEFAULT 0.0,
            stock REAL DEFAULT 0.0,
            unidad_medida TEXT NOT NULL,
            codigo TEXT DEFAULT '',
            id_proveedor INTEGER,
            FOREIGN KEY(id_proveedor) REFERENCES proveedores(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            obra TEXT NOT NULL,
            telefono TEXT,
            saldo_deuda REAL DEFAULT 0.0,
            activo INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boletas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT NOT NULL,
            fecha TEXT NOT NULL,
            total REAL NOT NULL,
            items TEXT NOT NULL,
            tipo_pago TEXT DEFAULT 'Efectivo',
            id_cliente INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS acopios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER NOT NULL,
            id_producto INTEGER NOT NULL,
            cantidad_acopiada REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_acopios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER NOT NULL,
            id_producto INTEGER NOT NULL,
            tipo_movimiento TEXT NOT NULL,
            cantidad REAL NOT NULL,
            fecha TEXT NOT NULL
        )
    ''')
    
    # 2. Carga automática de datos iniciales (Solo si las tablas están vacías)
    cursor.execute("SELECT COUNT(*) FROM proveedores")
    if cursor.fetchone()[0] == 0:
        proveedores_demo = [
            ("Loma Negra S.A.", "11-4567-8901 (Ventas Directas)"),
            ("Cantera Quilmes", "11-3344-5566 (Fletero Rodolfo)"),
            ("Distribuidora de Hierros Sur", "11-9988-7766 (Oficina Central)")
        ]
        cursor.executemany("INSERT INTO proveedores (nombre, contacto) VALUES (?, ?)", proveedores_demo)

    cursor.execute("SELECT COUNT(*) FROM clientes")
    if cursor.fetchone()[0] == 0:
        clientes_demo = [
            ("Juan Pérez", "Obra Av. Mitre 1420", "1123456789", 0.0, 1),
            ("Constructora Olivos SRL", "Edificio Calle Gorriti 450", "1165432109", 145000.0, 1),
            ("Roberto Gómez", "Refacción Casa Ituzaingó", "1144556677", 0.0, 1)
        ]
        cursor.executemany("INSERT INTO clientes (nombre, obra, telefono, saldo_deuda, activo) VALUES (?, ?, ?, ?, ?)", clientes_demo)

    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] == 0:
        # Formato: (categoria, descripcion, precio_costo, porcentaje_ganancia, precio_venta, stock, unidad, codigo, id_proveedor)
        productos_demo = [
            ("Bolsas", "Cemento Loma Negra x 50kg", 7000.0, 35.0, 9450.0, 150.0, "Unidad", "10", 1),
            ("Bolsas", "Cal Hidratada Cacique x 25kg", 3200.0, 40.0, 4480.0, 80.0, "Unidad", "11", 1),
            ("Bolsas", "Plasticor x 40kg", 5500.0, 30.0, 7150.0, 100.0, "Unidad", "12", 1),
            ("Ladrillos", "Ladrillo Hueco 12x18x33 (x Mil)", 220000.0, 30.0, 286000.0, 12.0, "Unidad", "20", 2),
            ("Ladrillos", "Ladrillo Hueco 18x18x33 (x Mil)", 310000.0, 30.0, 403000.0, 8.0, "Unidad", "21", 2),
            ("Ladrillos", "Ladrillo Común de Campo (x Mil)", 110000.0, 35.0, 148500.0, 15.0, "Unidad", "22", 2),
            ("Áridos", "Arena Fina en Bolsón", 18000.0, 40.0, 25200.0, 25.0, "Unidad", "30", 2),
            ("Áridos", "Piedra Partida 1-3 en Bolsón", 28000.0, 35.0, 37800.0, 18.0, "Unidad", "31", 2),
            ("Áridos", "Cascote Picado en Bolsón", 14000.0, 40.0, 19600.0, 30.0, "Unidad", "32", 2),
            ("Hierros", "Hierro del 8 mm (Barra 12m)", 8500.0, 30.0, 11050.0, 90.0, "Unidad", "40", 3),
            ("Hierros", "Hierro del 10 mm (Barra 12m)", 13200.0, 30.0, 17160.0, 75.0, "Unidad", "41", 3),
            ("Hierros", "Hierro del 12 mm (Barra 12m)", 19000.0, 30.0, 24700.0, 50.0, "Unidad", "42", 3),
            ("Hierros", "Malla Sima 15x15 (2x3m) 4.2mm", 22000.0, 35.0, 29700.0, 40.0, "Unidad", "43", 3),
            ("Bolsas", "Pegamento Klaukol x 30kg", 11500.0, 30.0, 14950.0, 60.0, "Unidad", "13", 1),
            ("Áridos", "Medares / Malla de Polietileno", 4500.0, 45.0, 6525.0, 45.0, "Unidad", "33", 2)
        ]
        cursor.executemany('''
            INSERT INTO productos (categoria, descripcion, precio_costo, porcentaje_ganancia, precio, stock, unidad_medida, codigo, id_proveedor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', productos_demo)

    conexion.commit()
    conexion.close()

# Ejecutar la creación e inserción al iniciar
inicializar_db()


# --- FUNCIÓN LOGÍSTICA PARA DISEÑAR EL COMPROBANTE PDF ---
def generar_pdf_boleta(id_boleta, cliente, destino, total, items, telefono_cliente="", descuento_porcentaje=0, localidad_cliente=""):
    nombre_archivo = f"Boleta_{id_boleta}.pdf"
    ruta_completa_pdf = os.path.join(CARPETA_PDFS, nombre_archivo)
    
    doc = SimpleDocTemplate(ruta_completa_pdf, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor("#2d3748"))
    style_linea_punteada = ParagraphStyle('Punteada', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor("#2d3748"))
    style_tabla_header = ParagraphStyle('TH', parent=styles['Normal'], fontSize=10, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    
    now = datetime.now()
    fecha_formateada = f"Fecha...{now.strftime('%d')}.../...{now.strftime('%m')}.../......{now.strftime('%Y')}......"
    
    if isinstance(id_boleta, int):
        num_boleta_str = f"{id_boleta:08d}"
    elif str(id_boleta).isdigit():
        num_boleta_str = f"{int(id_boleta):08d}"
    else:
        num_boleta_str = str(id_boleta)

    if getattr(sys, 'frozen', False):
        ruta_logo = os.path.join(sys._MEIPASS, 'logo.jpg')
    else:
        ruta_logo = os.path.join(BASE_DIR, 'logo.jpg')
        
    if os.path.exists(ruta_logo):
        img_aux = Image(ruta_logo)
        ancho_real = img_aux.imageWidth
        alto_real = img_aux.imageHeight
        ancho_deseado = 65 
        escala = ancho_deseado / ancho_real
        alto_proporcional = alto_real * escala
        logo_img = Image(ruta_logo, width=ancho_deseado, height=alto_proporcional)
        
        texto_contacto = Paragraph("<font size=9.5><b>📞 11-6871-6551<br/>📞 11-6493-8355</b><br/><font color='#2d3748'>materiales<b>online</b>.ar</font></font>", style_normal)
        
        t_logo_contacto = Table([[logo_img, texto_contacto]], colWidths=[75, 185])
        t_logo_contacto.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 0)
        ]))
        columna_izquierda = [t_logo_contacto]
    else:
        columna_izquierda = [
            Paragraph("<font size=16><b>materiales</b><br/>online</font>", style_normal),
            Spacer(1, 4),
            Paragraph("<font size=9><b>📞 11-6871-6551<br/>📞 11-6493-8355</b><br/><font color='#2d3748'>materiales<b>online</b>.ar</font></font>", style_normal)
        ]

    columna_derecha = [
        Paragraph("presupuesto", ParagraphStyle('TipoDoc', parent=styles['Normal'], fontSize=18, fontName="Helvetica-Bold", leading=20, alignment=1, textColor=colors.black)),
        Spacer(1, 2),
        Paragraph("(documento no válido como factura)", ParagraphStyle('SubDocHead', parent=styles['Normal'], fontSize=7.5, fontName="Helvetica", leading=9, alignment=1, textColor=colors.HexColor("#4a5568"))),
        Spacer(1, 8),
        Paragraph(f"<b>Nº- {num_boleta_str}</b>", ParagraphStyle('NumDoc', parent=styles['Normal'], fontSize=14, fontName="Helvetica-Bold", leading=16, alignment=1)),
        Spacer(1, 6),
        Paragraph(fecha_formateada, ParagraphStyle('FechaDoc', parent=styles['Normal'], fontSize=8.5, leading=10, alignment=1, textColor=colors.HexColor("#2d3748")))
    ]

    t_header = Table([[columna_izquierda, columna_derecha]], colWidths=[260, 260])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'CENTER'),
        ('LINEBELOW', (0,0), (-1,-1), 1, colors.HexColor("#2d3748"))
    ]))
    story.append(t_header)
    story.append(Spacer(1, 12))
    
    destino_texto = destino if destino else ""
    tel_texto = telefono_cliente if telefono_cliente else ""
    loc_texto = localidad_cliente if localidad_cliente else ""
    
    cliente_data = [
        [Paragraph(f"Señor: ..<b>{cliente}</b>", style_linea_punteada), ""],
        [Paragraph(f"Domicilio: ..<b>{destino_texto}</b>", style_linea_punteada), ""],
        [Paragraph(f"Localidad: ..<b>{loc_texto}</b>...........................................", style_linea_punteada), 
         Paragraph(f"Contacto: ..<b>{tel_texto}</b>.....................................................", style_linea_punteada)]
    ]
    
    t_cliente = Table(cliente_data, colWidths=[260, 260])
    t_cliente.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)), 
        ('SPAN', (0, 1), (1, 1)), 
        ('PADDING', (0,0), (-1,-1), 3), 
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]))
    story.append(t_cliente)
    story.append(Spacer(1, 12))
    
    tabla_items_data = [[
        Paragraph("cantidad", style_tabla_header),
        Paragraph("detalle", style_tabla_header),
        Paragraph("precio x u.", style_tabla_header),
        Paragraph("importe", style_tabla_header)
    ]]
    
    for item in items:
        sub_calc = float(item['precio']) * float(item['cantidad'])
        tabla_items_data.append([
            Paragraph(str(item['cantidad']), ParagraphStyle('TCant', parent=style_normal, alignment=1)),
            Paragraph(item['descripcion'], style_normal),
            Paragraph(f"${float(item['precio']):,.2f}", ParagraphStyle('TPrecio', parent=style_normal, alignment=2)),
            Paragraph(f"${sub_calc:,.2f}", ParagraphStyle('TImporte', parent=style_normal, alignment=2))
        ])
    
    filas_vacias = 6 if descuento_porcentaje > 0 else 7
    filas_vacias = filas_vacias - len(items)
    
    for _ in range(max(0, filas_vacias)):
        tabla_items_data.append([
            Paragraph("", style_normal), 
            Paragraph("", style_normal), 
            Paragraph("", style_normal), 
            Paragraph("", style_normal)
        ])
        
    if descuento_porcentaje > 0:
        factor = (100 - descuento_porcentaje) / 100
        subtotal_antes = total / factor if factor > 0 else total
        descuento_monto = subtotal_antes - total
        tabla_items_data.append(["", "", Paragraph("Subtotal:", ParagraphStyle('SubTxt', parent=style_normal, alignment=2)), Paragraph(f"${subtotal_antes:,.2f}", ParagraphStyle('SubNum', parent=style_normal, alignment=2))])
        tabla_items_data.append(["", "", Paragraph(f"Desc. {descuento_porcentaje}%:", ParagraphStyle('DescTxt', parent=style_normal, alignment=2)), Paragraph(f"-${descuento_monto:,.2f}", ParagraphStyle('DescNum', parent=style_normal, alignment=2, textColor=colors.HexColor("#e53e3e")))])

    tabla_items_data.append([Paragraph("DEVOLUCIÓN DE BOLSÓN DENTRO DE LOS 20 DÍAS CON SU RESPECTIVA SEÑA. FECHA ENTREGA", ParagraphStyle('Notita', parent=styles['Normal'], fontSize=6.5, fontName="Helvetica-Bold")), "", Paragraph("<b>TOTAL:</b>", ParagraphStyle('TotalTxt', parent=style_normal, alignment=2)), Paragraph(f"<b>${total:,.2f}</b>", ParagraphStyle('TotalNum', parent=style_normal, fontSize=11, alignment=2, textColor=colors.black))])
    
    alturas_filas = [22] + [32] * (len(items) + max(0, filas_vacias))
    if descuento_porcentaje > 0:
        alturas_filas += [None, None]
    alturas_filas += [None]
    
    t_items = Table(tabla_items_data, colWidths=[65, 255, 100, 100], rowHeights=alturas_filas)
    
    estilos_tabla = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#222222")), 
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), 
        ('GRID', (0,0), (-1,-2), 0.5, colors.HexColor("#cbd5e0")), 
        ('PADDING', (0,0), (-1,-1), 5), 
        ('SPAN', (0, -1), (1, -1)), 
        ('BOX', (0, -1), (1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ('LINEBELOW', (0, -1), (1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ('LINEABOVE', (2, -1), (3, -1), 1, colors.black)
    ]
    if descuento_porcentaje > 0:
        estilos_tabla.append(('SPAN', (0, -3), (1, -3)))
        estilos_tabla.append(('SPAN', (0, -2), (1, -2)))
        estilos_tabla.append(('BOX', (0, -3), (1, -2), 0.5, colors.HexColor("#cbd5e0")))
        
    t_items.setStyle(TableStyle(estilos_tabla))
    story.append(t_items)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Av. Pres. Perón 6699, Villa Udaondo, Ituzaingó", ParagraphStyle('Dir', parent=styles['Normal'], fontSize=10.5, fontName="Helvetica", alignment=1, textColor=colors.HexColor("#1a202c"))))
    
    doc.build(story)
    return nombre_archivo


# --- EMISIÓN ---
@app.route('/api/emitir-boleta', methods=['POST'])
def emitir_boleta():
    datos = request.json
    cliente = datos.get('cliente')
    destino = datos.get('destino')
    telefono_cliente = datos.get('telefono_cliente', '')
    localidad_cliente = datos.get('localidad_cliente', '') 
    items = datos.get('items')
    total = float(datos.get('total'))
    tipo_pago = datos.get('tipo_pago', 'Efectivo')
    id_cliente_cc = datos.get('id_cliente_cc')
    descuento_porcentaje = int(datos.get('descuento_porcentaje', 0))
    
    guardar_registro = datos.get('guardar_registro', True)
    descontar_stock = datos.get('descontar_stock', False)
    
    if not guardar_registro:
        id_falso = f"TEMP-{datetime.now().strftime('%M%S')}"
        archivo_pdf = generar_pdf_boleta(id_falso, cliente, destino, total, items, telefono_cliente, descuento_porcentaje, localidad_cliente)
        return jsonify({"status": "success", "archivo": archivo_pdf, "id_boleta": 0, "guardado": False})

    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items_json = json.dumps(items)
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO boletas (cliente, fecha, total, items, tipo_pago, id_cliente)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (cliente, fecha_actual, total, items_json, tipo_pago, id_cliente_cc))
        id_boleta = cursor.lastrowid
        
        if descontar_stock:
            for item in items:
                cursor.execute('UPDATE productos SET stock = stock - ? WHERE id = ?', (float(item['cantidad']), int(item['id'])))
            
        if tipo_pago == 'Cuenta Corriente' and id_cliente_cc:
            cursor.execute('UPDATE clientes SET saldo_deuda = saldo_deuda + ? WHERE id = ?', (total, int(id_cliente_cc)))
            
        conexion.commit()
        archivo_pdf = generar_pdf_boleta(f"{id_boleta:08d}", cliente, destino, total, items, telefono_cliente, descuento_porcentaje, localidad_cliente)
        return jsonify({"status": "success", "archivo": archivo_pdf, "id_boleta": id_boleta, "guardado": True})
    except Exception as e:
        conexion.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conexion.close()


# --- RUTAS WEB ---
@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/productos')
def administrar_productos():
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT p.id, p.codigo, p.categoria, p.descripcion, p.precio, p.precio_costo, p.stock, p.unidad_medida, p.porcentaje_ganancia, prov.nombre
        FROM productos p
        LEFT JOIN proveedores prov ON p.id_proveedor = prov.id
        ORDER BY p.categoria, p.descripcion
    ''')
    lista_productos = cursor.fetchall()
    
    cursor.execute("SELECT id, nombre, contacto FROM proveedores ORDER BY nombre")
    lista_proveedores = cursor.fetchall()
    conexion.close()
    return render_template('productos.html', productos=lista_productos, proveedores=lista_proveedores)

@app.route('/clientes')
def administrar_clientes():
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, obra, telefono, saldo_deuda FROM clientes WHERE activo = 1 ORDER BY nombre")
    clientes_raw = cursor.fetchall()
    lista_clientes = []
    for cli in clientes_raw:
        cursor.execute("SELECT id, fecha, total, tipo_pago FROM boletas WHERE id_cliente = ? ORDER BY id DESC", (cli[0],))
        boletas_raw = cursor.fetchall()
        boletas_cliente = [{"id": b[0], "fecha": b[1], "total": b[2], "estado": "Pendiente" if b[3] == 'Cuenta Corriente' else "Pagado"} for b in boletas_raw]
        lista_clientes.append({"id": cli[0], "nombre": cli[1], "obra": cli[2], "telefono": cli[3], "saldo": cli[4], "boletas": boletas_cliente})
    conexion.close()
    return render_template('clientes.html', clientes=lista_clientes)


# --- ENDPOINTS PROVEEDORES ---
@app.route('/guardar-proveedor', methods=['POST'])
def guardar_proveedor():
    nombre = request.form.get('nombre').strip()
    contacto = request.form.get('contacto', '').strip()
    if nombre:
        conexion = sqlite3.connect(DB_PATH)
        cursor = conexion.cursor()
        cursor.execute('INSERT INTO proveedores (nombre, contacto) VALUES (?, ?)', (nombre, contacto))
        conexion.commit()
        conexion.close()
    return redirect('/productos')


# --- ENDPOINTS PRODUCTOS ---
@app.route('/guardar-producto', methods=['POST'])
def guardar_producto():
    id_producto = request.form.get('id')
    codigo = request.form.get('codigo', '').strip()
    categoria = request.form.get('categoria').strip()
    descripcion = request.form.get('descripcion').strip()
    precio_costo = float(request.form.get('precio_costo') or 0.0)
    porcentaje_ganancia = float(request.form.get('porcentaje_ganancia') or 0.0)
    stock = float(request.form.get('stock') or 0.0)
    unidad_medida = request.form.get('unidad_medida')
    id_proveedor = request.form.get('id_proveedor')
    
    precio_venta = precio_costo + (precio_costo * (porcentaje_ganancia / 100))
    
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    if id_producto:
        cursor.execute('''
            UPDATE productos SET codigo = ?, categoria = ?, descripcion = ?, precio = ?, precio_costo = ?, porcentaje_ganancia = ?, stock = ?, unidad_medida = ?, id_proveedor = ? WHERE id = ?
        ''', (codigo, categoria, descripcion, precio_venta, precio_costo, porcentaje_ganancia, stock, unidad_medida, id_proveedor, id_producto))
    else:
        cursor.execute('''
            INSERT INTO productos (codigo, categoria, descripcion, precio, precio_costo, porcentaje_ganancia, stock, unidad_medida, id_proveedor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (codigo, categoria, descripcion, precio_venta, precio_costo, porcentaje_ganancia, stock, unidad_medida, id_proveedor))
    conexion.commit()
    conexion.close()
    return redirect('/productos')


# --- INTERFACES API ---
@app.route('/api/get-productos')
def get_productos_json():
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute("SELECT id, codigo, categoria, descripcion, precio, stock FROM productos")
    filas = cursor.fetchall()
    conexion.close()
    return jsonify([{"id": f[0], "codigo": f[1], "categoria": f[2], "descripcion": f[3], "precio": f[4], "stock": f[5]} for f in filas])

@app.route('/api/get-clientes-activos')
def get_clientes_activos():
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, obra, telefono, saldo_deuda FROM clientes WHERE activo = 1 ORDER BY nombre")
    filas = cursor.fetchall()
    conexion.close()
    return jsonify([{"id": f[0], "nombre": f[1], "obra": f[2], "telefono": f[3], "saldo": f[4]} for f in filas])


# --- APIS DE ACOPIO CON SISTEMA DE HISTORIAL ---
@app.route('/api/obtener-acopio/<int:id_cliente>')
def obtener_acopio(id_cliente):
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT a.id, p.descripcion, a.cantidad_acopiada, p.id
        FROM acopios a
        JOIN productos p ON a.id_producto = p.id
        WHERE a.id_cliente = ? AND a.cantidad_acopiada > 0
    ''', (id_cliente,))
    filas = cursor.fetchall()
    conexion.close()
    return jsonify([{"id_acopio": f[0], "descripcion": f[1], "cantidad": f[2], "id_producto": f[3]} for f in filas])

@app.route('/api/cargar-acopio', methods=['POST'])
def cargar_acopio():
    datos = request.json
    id_cliente = datos['id_cliente']
    id_producto = datos['id_producto']
    cantidad = float(datos['cantidad'])
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    
    cursor.execute("SELECT id FROM acopios WHERE id_cliente = ? AND id_producto = ?", (id_cliente, id_producto))
    fila = cursor.fetchone()
    if fila:
        cursor.execute("UPDATE acopios SET cantidad_acopiada = cantidad_acopiada + ? WHERE id = ?", (cantidad, fila[0]))
    else:
        cursor.execute("INSERT INTO acopios (id_cliente, id_producto, cantidad_acopiada) VALUES (?, ?, ?)", (id_cliente, id_producto, cantidad))
    
    cursor.execute('''
        INSERT INTO historial_acopios (id_cliente, id_producto, tipo_movimiento, cantidad, fecha)
        VALUES (?, ?, 'CARGA', ?, ?)
    ''', (id_cliente, id_producto, cantidad, fecha_actual))

    conexion.commit()
    conexion.close()
    return jsonify({"status": "success"})

@app.route('/api/retirar-acopio', methods=['POST'])
def retirar_acopio():
    datos = request.json
    id_acopio = datos['id_acopio']
    cantidad = float(datos['cantidad'])
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute("SELECT id_cliente, id_producto, cantidad_acopiada FROM acopios WHERE id = ?", (id_acopio,))
    fila = cursor.fetchone()
    
    if fila:
        id_cliente, id_producto, stock_actual = fila[0], fila[1], fila[2]
        
        cursor.execute("UPDATE acopios SET cantidad_acopiada = ? WHERE id = ?", (stock_actual - cantidad, id_acopio))
        cursor.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (cantidad, id_producto))
        
        cursor.execute('''
            INSERT INTO historial_acopios (id_cliente, id_producto, tipo_movimiento, cantidad, fecha)
            VALUES (?, ?, 'RETIRO', ?, ?)
        ''', (id_cliente, id_producto, cantidad, fecha_actual))

        conexion.commit()
    conexion.close()
    return jsonify({"status": "success"})

@app.route('/api/obtener-historial-acopio/<int:id_cliente>')
def obtener_historial_acopio(id_cliente):
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT h.fecha, p.descripcion, h.tipo_movimiento, h.cantidad
        FROM historial_acopios h
        JOIN productos p ON h.id_producto = p.id
        WHERE h.id_cliente = ?
        ORDER BY h.id DESC
    ''', (id_cliente,))
    filas = cursor.fetchall()
    conexion.close()
    return jsonify([
        {"fecha": f[0], "producto": f[1], "tipo": f[2], "cantidad": f[3]} 
        for f in filas
    ])


# --- CLIENTES Y DESCARGAS ---
@app.route('/guardar-cliente', methods=['POST'])
def guardar_cliente():
    id_cliente = request.form.get('id')
    nombre = request.form.get('nombre').strip()
    obra = request.form.get('obra').strip()
    telefono = request.form.get('telefono').strip()
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    if id_cliente:
        cursor.execute('UPDATE clientes SET nombre = ?, obra = ?, telefono = ? WHERE id = ?', (nombre, obra, telefono, id_cliente))
    else:
        cursor.execute('INSERT INTO clientes (nombre, obra, telefono, saldo_deuda, activo) VALUES (?, ?, ?, 0.0, 1)', (nombre, obra, telefono))
    conexion.commit()
    conexion.close()
    return redirect('/clientes')

@app.route('/descargar-pdf/<nombre_archivo>')
def descargar_pdf_archivo(nombre_archivo):
    return send_file(os.path.join(CARPETA_PDFS, nombre_archivo), as_attachment=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
