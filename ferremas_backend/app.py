from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS
from models import db, Producto, Sucursal, Venta, Inventario
import time
import threading
import grpc
from concurrent import futures
import ferremas_pb2
import ferremas_pb2_grpc

# Configuración Flask
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)
db.init_app(app)

# Inicializar base de datos y datos de prueba
with app.app_context():
    db.create_all()

    if not Producto.query.first():
        db.session.add_all([
            Producto(nombre="Taladro Bosch", precio=50000),
            Producto(nombre="Martillo Stanley", precio=15000)
        ])

    if not Sucursal.query.first():
        db.session.add_all([
            Sucursal(nombre="Sucursal Santiago", direccion="Av. Principal 123"),
            Sucursal(nombre="Sucursal Valparaíso", direccion="Calle Marina 456")
        ])

    if not Inventario.query.first():
        db.session.add_all([
            Inventario(producto_id=1, sucursal_id=1, stock=10),
            Inventario(producto_id=1, sucursal_id=2, stock=5),
            Inventario(producto_id=2, sucursal_id=1, stock=2),
            Inventario(producto_id=2, sucursal_id=2, stock=8),
        ])

    db.session.commit()

# Rutas REST
@app.route('/simular-compra', methods=['POST'])
def simular_compra():
    data = request.json
    sucursal_id = data['sucursal_id']
    productos_solicitados = data['productos']

    errores = []
    total = 0
    for item in productos_solicitados:
        producto = db.session.get(Producto, item['producto_id'])
        inventario = Inventario.query.filter_by(producto_id=producto.id, sucursal_id=sucursal_id).first()
        if not producto or not inventario:
            errores.append(f"Producto {item['producto_id']} no disponible en sucursal {sucursal_id}")
            continue
        if inventario.stock < item['cantidad']:
            errores.append(f"Stock insuficiente para producto {producto.nombre}")
        total += producto.precio * int(item['cantidad'])

    if errores:
        return jsonify({'success': False, 'errores': errores}), 400

    for item in productos_solicitados:
        inventario = Inventario.query.filter_by(producto_id=item['producto_id'], sucursal_id=sucursal_id).first()
        inventario.stock -= item['cantidad']
        db.session.add(Venta(
            producto_id=item['producto_id'],
            cantidad=item['cantidad'],
            sucursal_id=sucursal_id
        ))
    db.session.commit()

    return jsonify({'success': True, 'total': total})

@app.route('/productos')
def obtener_productos():
    sucursal_id = request.args.get('sucursal_id', type=int)
    inventario = Inventario.query.filter_by(sucursal_id=sucursal_id).all() if sucursal_id else Inventario.query.all()
    return jsonify([{
        'id': i.producto.id,
        'nombre': i.producto.nombre,
        'precio': i.producto.precio,
        'stock': i.stock
    } for i in inventario])

@app.route('/sucursales')
def obtener_sucursales():
    sucursales = Sucursal.query.all()
    return jsonify([{
        'id': s.id,
        'nombre': s.nombre,
        'direccion': s.direccion
    } for s in sucursales])

@app.route('/stock-alerta')
def stock_alerta():
    def eventos():
        with app.app_context():
            while True:
                inventario_bajo = Inventario.query.filter(Inventario.stock < 1).all()
                for inv in inventario_bajo:
                    yield f"data: {inv.producto.nombre} en {inv.sucursal.nombre} tiene stock bajo ({inv.stock})\n\n"
                time.sleep(10)
    return Response(eventos(), mimetype='text/event-stream')

@app.route('/ventas-simuladas', methods=['POST'])
def ventas_simuladas():
    try:
        data = request.json
        sucursal_id = data['sucursal_id']
        productos = data['productos']

        for item in productos:
            inv = Inventario.query.filter_by(
                producto_id=item['producto_id'],
                sucursal_id=sucursal_id
            ).first()

            if not inv or inv.stock < item['cantidad']:
                return jsonify({'error': f"Stock insuficiente para producto {item['producto_id']}"}), 400

            inv.stock -= item['cantidad']
            db.session.add(Venta(
                producto_id=item['producto_id'],
                cantidad=item['cantidad'],
                sucursal_id=sucursal_id
            ))

        db.session.commit()
        return jsonify({'mensaje': 'Compra simulada exitosa'}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Error en la simulación de compra'}), 500

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/confirmacion')
def confirmacion():
    return send_from_directory(app.static_folder, 'confirmacion.html')

@app.route('/agregar')
def agregar():
    return send_from_directory(app.static_folder, 'agregar.html')

@app.route('/agregar-producto', methods=['POST'])
def agregar_producto():
    data = request.json
    nombre = data.get('nombre')
    precio = data.get('precio')
    stock = data.get('stock')
    sucursal_id = data.get('sucursal_id')

    if not nombre or not precio or not stock or not sucursal_id:
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    try:
        # Crear el producto
        producto = Producto(nombre=nombre, precio=precio)
        db.session.add(producto)
        db.session.commit()

        # Crear inventario
        inventario = Inventario(producto_id=producto.id, sucursal_id=sucursal_id, stock=stock)
        db.session.add(inventario)
        db.session.commit()

        return jsonify({'mensaje': 'Producto agregado con éxito'}), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Error al agregar el producto'}), 500

class FerremasServiceServicer(ferremas_pb2_grpc.FerremasServiceServicer):
    def ListarProductos(self, request, context):
        with app.app_context():
            inventarios = Inventario.query.filter_by(sucursal_id=request.sucursal_id).all()
            productos = [
                ferremas_pb2.Producto(
                    id=i.producto.id,
                    nombre=i.producto.nombre,
                    precio=i.producto.precio,
                    stock=i.stock
                ) for i in inventarios
            ]
            return ferremas_pb2.ProductosResponse(productos=productos)

    def ListarSucursales(self, request, context):
        with app.app_context():
            sucursales = Sucursal.query.all()
            return ferremas_pb2.SucursalesResponse(sucursales=[
                ferremas_pb2.Sucursal(
                    id=s.id,
                    nombre=s.nombre,
                    direccion=s.direccion
                ) for s in sucursales
            ])

def iniciar_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    ferremas_pb2_grpc.add_FerremasServiceServicer_to_server(FerremasServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    print("🔌 Servidor gRPC iniciado en puerto 50051")
    server.start()
    server.wait_for_termination()

@app.route('/grpc/productos', methods=['GET'])
def grpc_productos():
    sucursal_id = request.args.get('sucursal_id', type=int)
    try:
        with grpc.insecure_channel('localhost:50051') as channel:
            stub = ferremas_pb2_grpc.FerremasServiceStub(channel)
            response = stub.ListarProductos(ferremas_pb2.SucursalRequest(sucursal_id=sucursal_id))
            productos = [{
                'id': p.id,
                'nombre': p.nombre,
                'precio': p.precio,
                'stock': p.stock
            } for p in response.productos]
        return jsonify(productos)
    except grpc.RpcError as e:
        print("❌ Error al conectar con gRPC:", e)
        return jsonify({'error': 'No se pudo conectar al servidor gRPC'}), 500

@app.route('/grpc/sucursales', methods=['GET'])
def grpc_sucursales():
    try:
        with grpc.insecure_channel('localhost:50051') as channel:
            stub = ferremas_pb2_grpc.FerremasServiceStub(channel)
            response = stub.ListarSucursales(ferremas_pb2.Empty())
            sucursales = [{
                'id': s.id,
                'nombre': s.nombre,
                'direccion': s.direccion
            } for s in response.sucursales]
        return jsonify(sucursales)
    except grpc.RpcError as e:
        print("❌ Error al conectar con gRPC:", e)
        return jsonify({'error': 'No se pudo conectar al servidor gRPC'}), 500

# ---------- INICIO ----------
if __name__ == '__main__':
    grpc_thread = threading.Thread(target=iniciar_grpc, daemon=True)
    grpc_thread.start()
    time.sleep(1) 
    app.run(debug=True)
