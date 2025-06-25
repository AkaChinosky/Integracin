import grpc
from concurrent import futures
import ferremas_pb2
import ferremas_pb2_grpc
from models import db, Producto, Inventario, Sucursal
from app import app  

class FerremasServiceServicer(ferremas_pb2_grpc.FerremasServiceServicer):
    def ListarProductos(self, request, context):
        with app.app_context():
            inventarios = Inventario.query.filter_by(sucursal_id=request.sucursal_id).all()
            productos = []
            for i in inventarios:
                productos.append(ferremas_pb2.Producto(
                    id=i.producto.id,
                    nombre=i.producto.nombre,
                    precio=i.producto.precio,
                    stock=i.stock
                ))
            return ferremas_pb2.ProductosResponse(productos=productos)

    def ListarSucursales(self, request, context):
        with app.app_context():
            sucursales = Sucursal.query.all()
            return ferremas_pb2.SucursalesResponse(sucursales=[
                ferremas_pb2.Sucursal(id=s.id, nombre=s.nombre, direccion=s.direccion)
                for s in sucursales
            ])

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    ferremas_pb2_grpc.add_FerremasServiceServicer_to_server(FerremasServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("gRPC server corriendo en puerto 50051...")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
