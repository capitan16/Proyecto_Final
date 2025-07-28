import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict
import queue

# Importar RoboDK 
try:
    from robodk.robolink import *
    from robodk.robomath import *
    ROBODK_AVAILABLE = True
    print("RoboDK importado correctamente")
except ImportError:
    print("Error: RoboDK no está instalado o no se puede importar")
    print("Instala RoboDK Python API: pip install robodk")
    ROBODK_AVAILABLE = False
    
    # Clases Mock para desarrollo sin RoboDK
    ITEM_TYPE_ROBOT = 1
    ITEM_TYPE_TARGET = 2
    
    class Robolink:
        def Item(self, name, item_type):
            return MockItem(name)
        
        def ItemUserPick(self, prompt, item_type):
            return MockItem("Robot_Mock")
        
        def getOpenStations(self):
            return ["Estacion_Mock"]
    
    class MockItem:
        def __init__(self, name):
            self.name = name
        
        def Valid(self):
            return True
        
        def Name(self):
            return self.name
        
        def Pose(self):
            return [0, 0, 0, 0, 0, 0]
        
        def MoveJ(self, pose):
            time.sleep(0.5)  # Simular tiempo de movimiento
            print(f"MOCK: Moviendo a {pose}")
        
        def MoveL(self, pose):
            time.sleep(0.4)  # Simular tiempo de movimiento lineal
            print(f"MOCK: Movimiento lineal a {pose}")
        
        def setSpeed(self, speed):
            print(f"MOCK: Velocidad establecida a {speed}")
        
        def setRounding(self, rounding):
            print(f"MOCK: Redondeo establecido a {rounding}")

class ArepaState(Enum):
    IDLE = "idle"                    # En bandeja de selección
    SELECTED = "selected"            # Seleccionada para cocción
    TRANSPORTING_TO_GRILL = "transporting_to_grill"
    COOKING_SIDE1 = "cooking_side1"  # Cocinando lado 1
    READY_TO_FLIP = "ready_to_flip"  # Lista para girar
    FLIPPING = "flipping"            # Girando
    COOKING_SIDE2 = "cooking_side2"  # Cocinando lado 2
    READY_TO_DELIVER = "ready_to_deliver"  # Lista para entrega
    TRANSPORTING_TO_DELIVERY = "transporting_to_delivery"
    DELIVERED = "delivered"          # Entregada
    ERROR = "error"                  # Error en el proceso

@dataclass
class ArepaInfo:
    id: str                          # A1, A2, A3, B1, B2, B3
    name: str                        # "Arepa de Queso", etc.
    state: ArepaState = ArepaState.IDLE
    grill_position: Optional[int] = None  # Posición en parrilla (1-4)
    cook_start_time: Optional[float] = None
    flip_time: Optional[float] = None
    delivery_time: Optional[float] = None
    selection_order: Optional[int] = None  # Orden de selección

class ArepaController:
    def __init__(self, root):
        self.root = root
        self.root.title("Control de Arepas - Parrilla Automática")
        self.root.geometry("900x650")  # Reducido de 1000x800
        self.root.resizable(True, True)
        
        # Inicializar log_text como None inicialmente
        self.log_text = None
        
        # RoboDK 
        if ROBODK_AVAILABLE:
            self.RDK = Robolink()
        else:
            self.RDK = Robolink()  # Usará la clase Mock
        self.robot = None
        
        # Sistema de control
        self.is_executing = False
        self.selected_arepas: List[str] = []  # Orden de selección
        self.grill_positions = [None, None, None, None]  # 4 posiciones de parrilla
        self.delivery_positions = [None, None, None, None]  # 4 posiciones de entrega
        
        # Tiempos de proceso (en segundos)
        self.cook_time_side1 = 10  # Reducido para testing
        self.cook_time_side2 = 10  # Reducido para testing
        
        # Definición de arepas
        self.arepas: Dict[str, ArepaInfo] = {
            "A1": ArepaInfo("A1", "Arepa de Queso"),
            "A2": ArepaInfo("A2", "Arepa de Pollo"),
            "A3": ArepaInfo("A3", "Arepa de Carne"),
            "B1": ArepaInfo("B1", "Arepa Mixta"),
            "B2": ArepaInfo("B2", "Arepa Vegetariana"),
            "B3": ArepaInfo("B3", "Arepa Especial")
        }
        
        # Control de timers por posición
        self.grill_timers = [None, None, None, None]
        self.timer_labels = []
        
        # Variables de control del proceso principal
        self.main_control_thread = None
        self.stop_control = False
        
        # Debug mode
        self.debug_mode = True
        
        # Crear interfaz PRIMERO
        self.create_interface()
        
        # Luego inicializar robot
        self.initialize_robot()
        
        # Iniciar actualización de timers
        self.update_timers()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def initialize_robot(self):
        """Inicializa la conexión con el robot"""
        try:
            if ROBODK_AVAILABLE:
                # Verificar que RoboDK esté corriendo
                stations = self.RDK.getOpenStations()
                if not stations:
                    self.log_message("ADVERTENCIA: RoboDK no tiene estaciones abiertas")
                    messagebox.showwarning("RoboDK", "RoboDK no tiene estaciones abiertas. Abre una estación primero.")
                    return False
                
                self.robot = self.RDK.ItemUserPick("Selecciona un robot", ITEM_TYPE_ROBOT)
                if not self.robot.Valid():
                    self.log_message("Error: No se ha seleccionado un robot válido.")
                    messagebox.showerror("Error", "No se ha seleccionado un robot válido en RoboDK.")
                    return False
                self.log_message(f"Robot seleccionado: {self.robot.Name()}")
            else:
                self.robot = self.RDK.ItemUserPick("Robot simulado", ITEM_TYPE_ROBOT)
                self.log_message("Usando robot simulado para testing")
            
            # Configurar robot
            self.robot.setSpeed(300)
            self.robot.setRounding(5)
            
            self.log_message("Robot inicializado correctamente.")
            return True
            
        except Exception as e:
            error_msg = f"Error al conectar con robot: {str(e)}"
            self.log_message(error_msg)
            if ROBODK_AVAILABLE:
                messagebox.showerror("Error RoboDK", error_msg)
            return False
    
    def create_interface(self):
        """Crea la interfaz gráfica compacta"""
        # Frame principal con scroll
        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Empaquetado del canvas
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        main_frame = ttk.Frame(scrollable_frame, padding="5")  # Reducido padding
        main_frame.pack(fill="both", expand=True)
        
        # Título más compacto
        title_label = ttk.Label(main_frame, text="Control de Arepas - Parrilla Automática", 
                               font=('Arial', 14, 'bold'))  # Reducido tamaño de fuente
        title_label.grid(row=0, column=0, columnspan=4, pady=(0, 10))  # Reducido pady
        
        # Panel de selección de arepas más compacto
        self.create_compact_selection_panel(main_frame)
        
        # Panel de orden más compacto
        self.create_compact_order_panel(main_frame)
        
        # Panel de parrilla más compacto
        self.create_compact_grill_panel(main_frame)
        
        # Panel de entrega más compacto
        self.create_compact_delivery_panel(main_frame)
        
        # Panel de control más compacto
        self.create_compact_control_panel(main_frame)
        
        # Panel de estado más compacto
        self.create_compact_status_panel(main_frame)
        
        # Configurar grid
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        main_frame.columnconfigure(3, weight=1)
    
    def create_compact_selection_panel(self, parent):
        """Crea el panel de selección de arepas más compacto"""
        selection_frame = ttk.LabelFrame(parent, text="Selección", padding="5")
        selection_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=2)
        
        self.arepa_buttons = {}
        self.arepa_vars = {}
        
        # Crear checkbuttons más compactos en una sola fila
        for i, arepa_id in enumerate(["A1", "A2", "A3", "B1", "B2", "B3"]):
            var = tk.BooleanVar()
            self.arepa_vars[arepa_id] = var
            
            # Texto más corto
            short_name = self.arepas[arepa_id].name.replace("Arepa de ", "").replace("Arepa ", "")
            btn = ttk.Checkbutton(selection_frame, 
                                 text=f"{arepa_id}:{short_name}",
                                 variable=var,
                                 command=self.on_arepa_selection_change)
            btn.grid(row=0, column=i, padx=5, pady=2, sticky="w")
            self.arepa_buttons[arepa_id] = btn
    
    def create_compact_order_panel(self, parent):
        """Crea el panel de orden más compacto"""
        order_frame = ttk.LabelFrame(parent, text="Orden", padding="5")
        order_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=2)
        
        self.order_label = ttk.Label(order_frame, text="Selecciona hasta 4 arepas", 
                                    font=('Arial', 9))
        self.order_label.grid(row=0, column=0, sticky="w")
    
    def create_compact_grill_panel(self, parent):
        """Crea el panel de parrilla más compacto"""
        grill_frame = ttk.LabelFrame(parent, text="Parrilla (1x4)", padding="5")
        grill_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=2)
        
        self.grill_labels = []
        self.timer_labels = []
        
        for i in range(4):
            # Frame más compacto para cada posición
            pos_frame = ttk.Frame(grill_frame)
            pos_frame.grid(row=0, column=i, padx=5, pady=2)
            
            # Etiqueta de posición más pequeña
            pos_label = ttk.Label(pos_frame, text=f"P{i+1}", font=('Arial', 8, 'bold'))
            pos_label.grid(row=0, column=0)
            
            # Etiqueta de arepa más compacta
            arepa_label = ttk.Label(pos_frame, text="Vacío", font=('Arial', 8), 
                                   background="lightgray", width=8, relief="sunken")
            arepa_label.grid(row=1, column=0, pady=1)
            self.grill_labels.append(arepa_label)
            
            # Etiqueta de timer más pequeña
            timer_label = ttk.Label(pos_frame, text="--:--", font=('Arial', 10, 'bold'), 
                                   foreground="red")
            timer_label.grid(row=2, column=0)
            self.timer_labels.append(timer_label)
    
    def create_compact_delivery_panel(self, parent):
        """Crea el panel de entrega más compacto"""
        delivery_frame = ttk.LabelFrame(parent, text="Entrega", padding="5")
        delivery_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=2)
        
        self.delivery_labels = []
        
        for i in range(4):
            # Frame más compacto
            pos_frame = ttk.Frame(delivery_frame)
            pos_frame.grid(row=0, column=i, padx=5, pady=2)
            
            # Etiqueta más pequeña
            pos_label = ttk.Label(pos_frame, text=f"E{i+1}", font=('Arial', 8, 'bold'))
            pos_label.grid(row=0, column=0)
            
            # Etiqueta de arepa más compacta
            arepa_label = ttk.Label(pos_frame, text="Vacío", font=('Arial', 8), 
                                   background="lightgray", width=8, relief="sunken")
            arepa_label.grid(row=1, column=0, pady=1)
            self.delivery_labels.append(arepa_label)
    
    def create_compact_control_panel(self, parent):
        """Crea el panel de control más compacto"""
        control_frame = ttk.LabelFrame(parent, text="Control", padding="5")
        control_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=2)
        
        # Primera fila de botones
        self.btn_start = ttk.Button(control_frame, text="Iniciar", 
                                   command=self.start_process, width=12)
        self.btn_start.grid(row=0, column=0, padx=2, pady=2)
        
        self.btn_stop = ttk.Button(control_frame, text="Detener", 
                                  command=self.stop_process, width=12)
        self.btn_stop.grid(row=0, column=1, padx=2, pady=2)
        self.btn_stop.configure(state="disabled")
        
        self.btn_home = ttk.Button(control_frame, text="Home", 
                                  command=self.go_to_home, width=12)
        self.btn_home.grid(row=0, column=2, padx=2, pady=2)
        
        self.btn_reset = ttk.Button(control_frame, text="Reset", 
                                   command=self.reset_system, width=12)
        self.btn_reset.grid(row=0, column=3, padx=2, pady=2)
        
        # Segunda fila de botones
        self.btn_check_robodk = ttk.Button(control_frame, text="Verificar RDK", 
                                          command=self.check_robodk_connection, width=12)
        self.btn_check_robodk.grid(row=1, column=0, padx=2, pady=2)
        
        self.btn_test_targets = ttk.Button(control_frame, text="Test Targets", 
                                          command=self.test_targets, width=12)
        self.btn_test_targets.grid(row=1, column=1, padx=2, pady=2)
    
    def create_compact_status_panel(self, parent):
        """Crea el panel de estado y log más compacto"""
        status_frame = ttk.LabelFrame(parent, text="Estado", padding="5")
        status_frame.grid(row=6, column=0, columnspan=4, sticky="ew", pady=2)
        
        # Estado general más compacto
        self.status_label = ttk.Label(status_frame, text="Sistema listo", 
                                     font=('Arial', 9, 'bold'))
        self.status_label.grid(row=0, column=0, sticky="w")
        
        # Log de actividad más compacto
        log_frame = ttk.LabelFrame(parent, text="Log", padding="5")
        log_frame.grid(row=7, column=0, columnspan=4, sticky="ew", pady=2)
        
        self.log_text = tk.Text(log_frame, height=8, width=70, font=('Consolas', 8))  # Reducido altura y fuente
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky="ew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        log_frame.columnconfigure(0, weight=1)
    
    def log_message(self, message):
        """Agrega un mensaje al log"""
        if self.log_text is None:
            print(f"LOG: {message}")
            return
            
        timestamp = time.strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, full_message)
        self.log_text.see(tk.END)
        
        # También imprimir en consola para debug
        if self.debug_mode:
            print(full_message.strip())
        
        self.root.update_idletasks()
    
    def update_status(self, status):
        """Actualiza el estado general"""
        if hasattr(self, 'status_label') and self.status_label:
            self.status_label.config(text=status)
            self.root.update_idletasks()
        else:
            print(f"STATUS: {status}")
    
    def on_arepa_selection_change(self):
        """Maneja cambios en la selección de arepas - ORDEN CORREGIDO"""
        if self.is_executing:
            return
        
        # Lista anterior
        previous_selected = self.selected_arepas.copy()
        
        # Obtener arepas actualmente marcadas
        currently_checked = []
        for arepa_id in ["A1", "A2", "A3", "B1", "B2", "B3"]:
            if self.arepa_vars[arepa_id].get():
                currently_checked.append(arepa_id)
        
        # Mantener orden anterior para las que siguen seleccionadas
        new_selected = []
        for arepa_id in previous_selected:
            if arepa_id in currently_checked:
                new_selected.append(arepa_id)
        
        # Agregar las nuevas al final
        for arepa_id in currently_checked:
            if arepa_id not in new_selected:
                new_selected.append(arepa_id)
        
        # Limitar a 4 arepas
        if len(new_selected) > 4:
            last_arepa = new_selected[-1]
            self.arepa_vars[last_arepa].set(False)
            new_selected = new_selected[:-1]
            messagebox.showwarning("Límite", "Solo se pueden seleccionar hasta 4 arepas")
        
        self.selected_arepas = new_selected
        
        # Asignar orden de selección
        for i, arepa_id in enumerate(self.selected_arepas):
            self.arepas[arepa_id].selection_order = i + 1
        
        # Limpiar orden de las no seleccionadas
        for arepa_id in self.arepas.keys():
            if arepa_id not in self.selected_arepas:
                self.arepas[arepa_id].selection_order = None
        
        # Actualizar display
        if self.selected_arepas:
            order_text = f"Orden: {' → '.join(self.selected_arepas)}"
        else:
            order_text = "Selecciona hasta 4 arepas"
        
        self.order_label.config(text=order_text)
    
    def test_targets(self):
        """Prueba que todos los targets necesarios existan"""
        if self.is_executing:
            messagebox.showwarning("Proceso activo", "No se puede probar targets durante la ejecución")
            return
        
        self.log_message("🔍 PROBANDO EXISTENCIA DE TARGETS...")
        
        # Lista de todos los targets necesarios
        required_targets = [
            "Home",
            # Posiciones intermedias
            "Pos1_Estan1", "Pos1_Estan2",
            # Estante 1
            "Estan1_1_Agarre", "Estan1_2_Agarre", "Estan1_3_Agarre",
            # Estante 2
            "Estan2_1_Agarre", "Estan2_2_Agarre", "Estan2_3_Agarre",
            # Parrilla - Posiciones normales
            "Parrilla_Pos1", "Parrilla_Pos2", "Parrilla_Pos3", "Parrilla_Pos4",
            "Parrilla_Arepa1", "Parrilla_Arepa2", "Parrilla_Arepa3", "Parrilla_Arepa4",
            # Parrilla - Posiciones de giro
            "Parrilla_Pos1_Giro", "Parrilla_Pos2_Giro", "Parrilla_Pos3_Giro", "Parrilla_Pos4_Giro",
            "Parrilla_Giro_Pos1", "Parrilla_Giro_Pos2", "Parrilla_Giro_Pos3", "Parrilla_Giro_Pos4",
            # Entrega - Target intermedio y posiciones finales
            "Entrega1",
            "Entrega_Pos1", "Entrega_Pos2", "Entrega_Pos3", "Entrega_Pos4"
        ]
        
        missing_targets = []
        existing_targets = []
        
        for target_name in required_targets:
            if self.check_target_exists(target_name):
                existing_targets.append(target_name)
                self.log_message(f"✓ {target_name}")
            else:
                missing_targets.append(target_name)
                self.log_message(f"✗ {target_name}")
        
        self.log_message(f"📊 Existentes: {len(existing_targets)}, Faltantes: {len(missing_targets)}")
        
        if missing_targets:
            messagebox.showerror("Targets Faltantes", 
                               f"Faltan {len(missing_targets)} targets.\nRevisa el log.")
        else:
            self.log_message("✅ TODOS LOS TARGETS DISPONIBLES")
            messagebox.showinfo("Test OK", "Todos los targets están disponibles")
    
    def check_target_exists(self, target_name: str) -> bool:
        """Verifica si un target existe"""
        try:
            if ROBODK_AVAILABLE:
                target = self.RDK.Item(target_name, ITEM_TYPE_TARGET)
                return target.Valid()
            else:
                # En modo simulación, asumimos que todos existen
                return True
        except Exception as e:
            return False
    
    def start_process(self):
        """Inicia el proceso de cocción"""
        if not self.selected_arepas:
            messagebox.showwarning("Sin selección", "Selecciona al menos una arepa antes de iniciar")
            return
        
        if self.is_executing:
            messagebox.showwarning("En proceso", "El sistema ya está ejecutando un proceso")
            return
        
        if not self.robot:
            messagebox.showerror("Error", "Robot no inicializado")
            return
        
        # Verificar targets críticos antes de iniciar
        critical_targets = ["Home", "Pos1_Estan1", "Pos1_Estan2", "Entrega1"]
        for target in critical_targets:
            if not self.check_target_exists(target):
                messagebox.showerror("Error", f"Target crítico '{target}' no encontrado")
                return
        
        self.is_executing = True
        self.stop_control = False
        
        # Deshabilitar botones
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        
        # Deshabilitar selección de arepas
        for btn in self.arepa_buttons.values():
            btn.configure(state="disabled")
        
        self.log_message("=" * 40)
        self.log_message("INICIANDO PROCESO DE COCCIÓN")
        self.log_message(f"Arepas: {' → '.join(self.selected_arepas)}")
        self.log_message("=" * 40)
        
        # Iniciar hilo principal de control
        self.main_control_thread = threading.Thread(target=self.main_control_loop, daemon=True)
        self.main_control_thread.start()
    
    def main_control_loop(self):
        """Bucle principal de control"""
        try:
            self.update_status("Iniciando proceso...")
            
            # Ir a Home primero
            if not self.move_to_target("Home"):
                self.log_message("✗ No se pudo ir a Home. Abortando.")
                return
            
            # FASE 1: TRANSPORTE DE TODAS LAS AREPAS A LA PARRILLA
            self.log_message("🔥 TRANSPORTANDO AREPAS A PARRILLA")
            
            for i, arepa_id in enumerate(self.selected_arepas):
                if self.stop_control:
                    self.log_message("🛑 Proceso detenido")
                    break
                    
                self.log_message(f"--- {arepa_id} ({i+1}/{len(self.selected_arepas)}) ---")
                
                success = self.transport_arepa_to_grill(arepa_id)
                if not success:
                    self.log_message(f"✗ Error transportando {arepa_id}")
                    self.arepas[arepa_id].state = ArepaState.ERROR
                    break
                
                self.update_grill_display()
                time.sleep(0.5)
            
            if not self.stop_control and all(self.arepas[aid].state != ArepaState.ERROR for aid in self.selected_arepas):
                self.log_message("✓ TODAS TRANSPORTADAS - COCINANDO")
                self.update_status("Cocinando - Lado 1...")
                self.process_cooking_phases()
        
        except Exception as e:
            self.log_message(f"✗ Error: {str(e)}")
        
        finally:
            self.cleanup_process()
    
    def process_cooking_phases(self):
        """Procesa las fases de cocción - CORREGIDO PARA PROCESAR TODAS LAS AREPAS"""
        try:
            while not self.stop_control:
                current_time = time.time()
                action_taken = False
                
                # Verificar arepas listas para voltear
                for i, timer_info in enumerate(self.grill_timers):
                    if timer_info is None:
                        continue
                    
                    arepa_id = timer_info['arepa_id']
                    arepa = self.arepas[arepa_id]
                    elapsed = current_time - timer_info['start_time']
                    
                    # Verificar volteo (lado 1 → lado 2)
                    if (timer_info['side'] == 1 and 
                        elapsed >= self.cook_time_side1 and 
                        arepa.state == ArepaState.COOKING_SIDE1):
                        
                        self.log_message(f"⏰ {arepa_id} listo para voltear")
                        if not self.stop_control:
                            if self.flip_arepa(arepa_id, i + 1):
                                action_taken = True
                    
                    # Verificar entrega (lado 2 → entrega)
                    elif (timer_info['side'] == 2 and 
                          elapsed >= self.cook_time_side2 and 
                          arepa.state == ArepaState.COOKING_SIDE2):
                        
                        self.log_message(f"⏰ {arepa_id} listo para entrega")
                        if not self.stop_control:
                            if self.deliver_arepa(arepa_id, i + 1):
                                action_taken = True
                                # *** FORZAR ACTUALIZACIÓN INMEDIATA DE DISPLAYS ***
                                self.update_grill_display()
                                self.update_delivery_display()
                                self.root.update_idletasks()  # Forzar actualización GUI
                
                # Verificar si todas las arepas están entregadas
                all_delivered = all(
                    self.arepas[arepa_id].state == ArepaState.DELIVERED 
                    for arepa_id in self.selected_arepas
                )
                
                if all_delivered:
                    self.log_message("🎉 TODAS ENTREGADAS - COMPLETADO")
                    self.update_status("Retornando a Home...")
                    
                    # *** ACTUALIZACIÓN FINAL DE DISPLAYS ANTES DE IR A HOME ***
                    self.update_grill_display()
                    self.update_delivery_display()
                    self.root.update_idletasks()
                    
                    # REGRESAR A HOME PASANDO POR ENTREGA1 (MOVIMIENTOS INTERMEDIOS)
                    self.log_message("🏠 REGRESANDO A HOME CON MOVIMIENTOS INTERMEDIOS")
                    if self.return_to_home_with_intermediate():
                        self.log_message("✓ Robot regresó a Home correctamente")
                        self.update_status("Proceso completado - Robot en Home")
                    else:
                        self.log_message("⚠️ Error regresando a Home")
                        self.update_status("Proceso completado - Error en Home")
                    
                    break
                
                # Actualizar displays
                if action_taken:
                    self.update_grill_display()
                    self.update_delivery_display()
                
                time.sleep(0.5)
                
        except Exception as e:
            self.log_message(f"✗ Error en cocción: {str(e)}")
    
    def transport_arepa_to_grill(self, arepa_id: str) -> bool:
        """Transporta una arepa desde su estante a la parrilla usando MoveL"""
        try:
            self.log_message(f"=== TRANSPORTANDO {arepa_id} ===")
            
            # Cambiar estado inmediatamente
            self.arepas[arepa_id].state = ArepaState.TRANSPORTING_TO_GRILL
            self.update_grill_display()
            
            # Obtener posición de parrilla
            grill_pos = self.assign_grill_position(arepa_id)
            if grill_pos is None:
                self.log_message(f"✗ Sin posición para {arepa_id}")
                return False
            
            self.log_message(f"Posición parrilla: {grill_pos}")
            
            # Definir secuencia de movimientos
            intermediate_pos = self.get_intermediate_position(arepa_id)
            source_pos = self.get_arepa_source_position(arepa_id)
            parrilla_intermediate = f"Parrilla_Pos{grill_pos}"
            parrilla_final = f"Parrilla_Arepa{grill_pos}"
            
            # Verificar que todos los targets existan
            required_targets = [intermediate_pos, source_pos, parrilla_intermediate, parrilla_final]
            for target in required_targets:
                if not self.check_target_exists(target):
                    self.log_message(f"✗ Target '{target}' no encontrado")
                    return False
            
            # Ejecutar secuencia de movimientos LINEALES
            movements = [
                (intermediate_pos, f"1. → {intermediate_pos}"),
                (source_pos, f"2. → {source_pos}"),
                (intermediate_pos, f"4. ← Intermedia"),
                (parrilla_intermediate, f"5. → {parrilla_intermediate}"),
                (parrilla_final, f"6. ↓ {parrilla_final}"),
                (parrilla_intermediate, f"7. ↑ Intermedia")
            ]
            
            for i, (target, description) in enumerate(movements):
                if self.stop_control:
                    self.log_message("🛑 Cancelado")
                    return False
                
                self.log_message(description)
                
                if not self.move_to_target_linear(target):
                    self.log_message(f"✗ Error en movimiento {i+1}")
                    return False
                
                # Simular operaciones especiales
                if i == 1:  # Después de llegar a source_pos
                    self.log_message(f"3. Tomando {arepa_id}")
                    time.sleep(1)
                elif i == 4:  # Después de llegar a parrilla_final
                    self.log_message(f"Colocando {arepa_id}")
                    time.sleep(1)
            
            # Actualizar estado e iniciar cocción
            self.arepas[arepa_id].state = ArepaState.COOKING_SIDE1
            self.arepas[arepa_id].cook_start_time = time.time()
            self.start_grill_timer(grill_pos, 1)
            
            self.log_message(f"✓ {arepa_id} EN POSICIÓN {grill_pos} - COCINANDO LADO 1")
            return True
            
        except Exception as e:
            self.log_message(f"✗ Error transportando {arepa_id}: {str(e)}")
            return False
    
    def flip_arepa(self, arepa_id: str, position: int) -> bool:
        """Voltea una arepa en la parrilla con movimientos lineales"""
        try:
            self.log_message(f"🔄 VOLTEANDO {arepa_id} POS {position}")
            
            self.arepas[arepa_id].state = ArepaState.FLIPPING
            self.update_grill_display()
            
            # Definir targets para la secuencia de volteo
            parrilla_pos = f"Parrilla_Pos{position}"
            parrilla_arepa = f"Parrilla_Arepa{position}"
            parrilla_pos_giro = f"Parrilla_Pos{position}_Giro"
            parrilla_giro_pos = f"Parrilla_Giro_Pos{position}"
            
            # Verificar targets
            required_targets = [parrilla_pos, parrilla_arepa, parrilla_pos_giro, parrilla_giro_pos]
            for target in required_targets:
                if not self.check_target_exists(target):
                    self.log_message(f"✗ Target '{target}' no encontrado")
                    return False
            
            # SECUENCIA DE VOLTEO CON MOVIMIENTOS LINEALES:
            self.log_message(f"🔄 Secuencia volteo {arepa_id}")
            
            movements = [
                (parrilla_pos, f"1. → {parrilla_pos}"),
                (parrilla_arepa, f"2. ↓ Tomar arepa"),
                (parrilla_pos, f"4. ↑ Con arepa"),
                (parrilla_pos_giro, f"5. 🔄 Rotar Z"),
                (parrilla_giro_pos, f"6. ↓ Dejar volteada"),
                (parrilla_pos_giro, f"8. ↑ Subir"),
                (parrilla_pos, f"9. 🔄 Rotar normal")
            ]
            
            for i, (target, description) in enumerate(movements):
                if self.stop_control:
                    return False
                
                self.log_message(description)
                
                # Usar movimiento de rotación para cambios de orientación
                if i in [3, 6]:  # Movimientos de rotación
                    if i == 3:  # Rotación para voltear
                        if not self.rotate_to_target(parrilla_pos, parrilla_pos_giro):
                            return False
                    else:  # Rotación de vuelta
                        if not self.rotate_to_target(parrilla_pos_giro, parrilla_pos):
                            return False
                else:
                    if not self.move_to_target_linear(target):
                        return False
                
                # Operaciones especiales
                if i == 1:  # Después de bajar
                    self.log_message(f"3. Agarrando {arepa_id}")
                    time.sleep(1)
                elif i == 4:  # Después de bajar volteada
                    self.log_message(f"7. Soltando {arepa_id} volteada")
                    time.sleep(1)
            
            # Actualizar estado e iniciar timer lado 2
            self.arepas[arepa_id].state = ArepaState.COOKING_SIDE2
            self.arepas[arepa_id].flip_time = time.time()
            self.start_grill_timer(position, 2)
            
            self.log_message(f"✓ {arepa_id} VOLTEADA - COCINANDO LADO 2")
            return True
            
        except Exception as e:
            self.log_message(f"✗ Error volteando {arepa_id}: {str(e)}")
            return False
    
    def deliver_arepa(self, arepa_id: str, grill_position: int) -> bool:
        """Entrega una arepa terminada con movimientos intermedios obligatorios"""
        try:
            self.log_message(f"📦 ENTREGANDO {arepa_id} POS {grill_position}")
            
            self.arepas[arepa_id].state = ArepaState.TRANSPORTING_TO_DELIVERY
            
            # Encontrar posición de entrega disponible
            delivery_pos = None
            for i in range(4):
                if self.delivery_positions[i] is None:
                    delivery_pos = i + 1
                    break
            
            if delivery_pos is None:
                self.log_message("✗ Sin posiciones de entrega")
                return False
            
            parrilla_intermediate = f"Parrilla_Pos{grill_position}"
            parrilla_final = f"Parrilla_Arepa{grill_position}"
            entrega_intermedio = "Entrega1"  # TARGET INTERMEDIO OBLIGATORIO
            entrega_pos = f"Entrega_Pos{delivery_pos}"
            
            # Verificar targets
            required_targets = [parrilla_intermediate, parrilla_final, entrega_intermedio, entrega_pos]
            for target in required_targets:
                if not self.check_target_exists(target):
                    self.log_message(f"✗ Target '{target}' no encontrado")
                    return False
            
            # SECUENCIA: Parrilla → Entrega1 → Entrega_Pos# → Entrega1 (para siguiente arepa)
            movements = [
                (parrilla_intermediate, f"1. → {parrilla_intermediate}"),
                (parrilla_final, f"2. ↓ Tomar terminada"),
                (parrilla_intermediate, f"4. ↑ Con arepa"),
                (entrega_intermedio, f"5. → {entrega_intermedio}"),  # PASO INTERMEDIO OBLIGATORIO
                (entrega_pos, f"6. → {entrega_pos}")
            ]
            
            for i, (target, description) in enumerate(movements):
                if self.stop_control:
                    return False
                
                self.log_message(description)
                
                if not self.move_to_target_linear(target):
                    self.log_message(f"✗ Error entregando")
                    return False
                
                if i == 1:  # Después de tomar la arepa
                    self.log_message(f"3. Tomando {arepa_id} terminada")
                    time.sleep(1)
                elif i == 4:  # Después de llegar a entrega final
                    self.log_message(f"7. Entregando {arepa_id} en E{delivery_pos}")
                    time.sleep(1)
            
            # MOVIMIENTO INTERMEDIO OBLIGATORIO: Regresar a Entrega1 después de entregar
            # (excepto si es la última arepa, que irá a Home)
            remaining_arepas = sum(1 for aid in self.selected_arepas 
                                 if self.arepas[aid].state != ArepaState.DELIVERED 
                                 and aid != arepa_id)
            
            if remaining_arepas > 0:
                self.log_message("8. → Entrega1 (posición intermedia)")
                if not self.move_to_target_linear(entrega_intermedio):
                    self.log_message("⚠️ Error regresando a posición intermedia")
                    # Continuar de todas formas
            
            # Actualizar estados
            self.arepas[arepa_id].state = ArepaState.DELIVERED
            self.arepas[arepa_id].delivery_time = time.time()
            
            # Liberar posición de parrilla
            self.grill_positions[grill_position - 1] = None
            self.grill_timers[grill_position - 1] = None
            
            # Ocupar posición de entrega
            self.delivery_positions[delivery_pos - 1] = arepa_id
            
            # *** AGREGAR ESTA LÍNEA PARA ACTUALIZAR EL DISPLAY DE ENTREGA ***
            self.update_delivery_display()
            
            self.log_message(f"✓ {arepa_id} ENTREGADA EN E{delivery_pos}")
            return True
            
        except Exception as e:
            self.log_message(f"✗ Error entregando {arepa_id}: {str(e)}")
            return False
    
    def return_to_home_with_intermediate(self) -> bool:
        """Regresa a Home pasando por Entrega1 - NUEVA FUNCIÓN"""
        try:
            self.log_message("🏠 SECUENCIA RETORNO A HOME CON INTERMEDIO")
            
            entrega_intermedio = "Entrega1"  # TARGET INTERMEDIO OBLIGATORIO
            home_target = "Home"
            
            # Verificar targets
            required_targets = [entrega_intermedio, home_target]
            for target in required_targets:
                if not self.check_target_exists(target):
                    self.log_message(f"✗ Target '{target}' no encontrado")
                    return False
            
            # SECUENCIA OBLIGATORIA: Posición actual → Entrega1 → Home
            movements = [
                (entrega_intermedio, f"1. → {entrega_intermedio} (intermedio)"),
                (home_target, f"2. → {home_target} (final)")
            ]
            
            for i, (target, description) in enumerate(movements):
                if self.stop_control:
                    return False
                
                self.log_message(description)
                
                # Para Home usar MoveJ, para intermedio usar MoveL
                if target == home_target:
                    if not self.move_to_target(target):  # MoveJ para Home
                        self.log_message(f"✗ Error yendo a Home")
                        return False
                else:
                    if not self.move_to_target_linear(target):  # MoveL para intermedio
                        self.log_message(f"✗ Error en movimiento intermedio")
                        return False
            
            self.log_message("✓ Secuencia Home completada con movimientos intermedios")
            return True
            
        except Exception as e:
            self.log_message(f"✗ Error regresando a Home: {str(e)}")
            return False
    
    def move_to_target_linear(self, target_name: str) -> bool:
        """Mueve el robot a un target usando MoveL (movimiento lineal)"""
        try:
            if ROBODK_AVAILABLE:
                # Verificar que el target existe
                target = self.RDK.Item(target_name, ITEM_TYPE_TARGET)
                if not target.Valid():
                    self.log_message(f"✗ Target '{target_name}' no encontrado")
                    return False
                
                pose = target.Pose()
                self.log_message(f"  → LINEAR: {target_name}")
                
                # Usar MoveL para movimiento lineal
                result = self.robot.MoveL(pose)
                
                self.log_message(f"  ✓ LINEAR OK: {target_name}")
                
            else:
                # Modo simulación
                self.log_message(f"  → SIM LINEAR: {target_name}")
                time.sleep(0.6)  # Tiempo simulado para movimiento lineal
                self.log_message(f"  ✓ SIM LINEAR OK: {target_name}")
            
            return True
            
        except Exception as e:
            error_msg = f"✗ Error MoveL a {target_name}: {str(e)}"
            self.log_message(error_msg)
            
            if ROBODK_AVAILABLE:
                messagebox.showerror("Error MoveL", 
                                   f"No se pudo hacer movimiento lineal a '{target_name}'.\n\nError: {str(e)}")
            
            return False
    
    def move_to_target(self, target_name: str) -> bool:
        """Mueve el robot a un target específico (mantiene MoveJ para Home y posiciones de seguridad)"""
        try:
            if ROBODK_AVAILABLE:
                target = self.RDK.Item(target_name, ITEM_TYPE_TARGET)
                if not target.Valid():
                    self.log_message(f"✗ Target '{target_name}' no encontrado")
                    return False
                
                pose = target.Pose()
                self.log_message(f"  → JOINT: {target_name}")
                
                # Usar MoveJ para movimientos articulares (Home, etc.)
                result = self.robot.MoveJ(pose)
                
                self.log_message(f"  ✓ JOINT OK: {target_name}")
                
            else:
                # Modo simulación
                self.log_message(f"  → SIM JOINT: {target_name}")
                time.sleep(0.8)
                self.log_message(f"  ✓ SIM JOINT OK: {target_name}")
            
            return True
            
        except Exception as e:
            error_msg = f"✗ Error MoveJ a {target_name}: {str(e)}"
            self.log_message(error_msg)
            
            if ROBODK_AVAILABLE:
                messagebox.showerror("Error MoveJ", 
                                   f"No se pudo mover a '{target_name}'.\n\nError: {str(e)}")
            
            return False
    
    def rotate_to_target(self, from_target: str, to_target: str) -> bool:
        """Realiza una rotación específica solo en eje Z entre dos targets usando MoveL"""
        try:
            if ROBODK_AVAILABLE:
                # Obtener poses de ambos targets
                target_from = self.RDK.Item(from_target, ITEM_TYPE_TARGET)
                target_to = self.RDK.Item(to_target, ITEM_TYPE_TARGET)
                
                if not target_from.Valid() or not target_to.Valid():
                    self.log_message(f"✗ Targets rotación inválidos: {from_target} -> {to_target}")
                    return False
                
                pose_to = target_to.Pose()
                
                self.log_message(f"  🔄 ROT LINEAR Z: {from_target} -> {to_target}")
                
                # Usar MoveJ para rotación suave
                self.robot.MoveJ(pose_to)
                
                self.log_message(f"  ✓ ROT OK: {to_target}")
                
            else:
                # Modo simulación
                self.log_message(f"  🔄 SIM ROT Z: {from_target} -> {to_target}")
                time.sleep(1.0)  # Simular tiempo de rotación
                self.log_message(f"  ✓ SIM ROT OK: {to_target}")
            
            return True
            
        except Exception as e:
            error_msg = f"✗ Error rotación {from_target} -> {to_target}: {str(e)}"
            self.log_message(error_msg)
            
            if ROBODK_AVAILABLE:
                messagebox.showerror("Error rotación", 
                                   f"No se pudo rotar.\n\nError: {str(e)}")
            
            return False
    
    def get_arepa_source_position(self, arepa_id: str) -> str:
        """Obtiene la posición de origen de una arepa"""
        if arepa_id.startswith('A'):
            pos_num = int(arepa_id[1])
            return f"Estan1_{pos_num}_Agarre"
        elif arepa_id.startswith('B'):
            pos_num = int(arepa_id[1])
            return f"Estan2_{pos_num}_Agarre"
        else:
            raise ValueError(f"ID de arepa inválido: {arepa_id}")
    
    def get_intermediate_position(self, arepa_id: str) -> str:
        """Obtiene la posición intermedia según el estante"""
        if arepa_id.startswith('A'):
            return "Pos1_Estan1"
        elif arepa_id.startswith('B'):
            return "Pos1_Estan2"
        else:
            raise ValueError(f"ID de arepa inválido: {arepa_id}")
    
    def get_available_grill_position(self) -> Optional[int]:
        """Obtiene la primera posición de parrilla disponible"""
        for i, arepa_id in enumerate(self.grill_positions):
            if arepa_id is None:
                return i + 1
        return None
    
    def assign_grill_position(self, arepa_id: str) -> Optional[int]:
        """Asigna una posición de parrilla a una arepa respetando el orden"""
        arepa = self.arepas[arepa_id]
        if arepa.selection_order is None:
            self.log_message(f"✗ Arepa {arepa_id} sin orden")
            return None
        
        # Intentar asignar en la posición correspondiente al orden
        preferred_position = arepa.selection_order
        
        if preferred_position <= 4 and self.grill_positions[preferred_position - 1] is None:
            position = preferred_position
        else:
            # Si no, buscar la primera disponible
            position = self.get_available_grill_position()
            if position is None:
                self.log_message("✗ Sin posiciones parrilla")
                return None
        
        self.grill_positions[position - 1] = arepa_id
        arepa.grill_position = position
        return position
    
    def start_grill_timer(self, position: int, side: int):
        """Inicia el timer visual de una posición de parrilla"""
        if position < 1 or position > 4:
            self.log_message(f"✗ Posición inválida: {position}")
            return
        
        arepa_id = self.grill_positions[position - 1]
        if arepa_id is None:
            self.log_message(f"✗ Sin arepa en posición {position}")
            return
        
        self.grill_timers[position - 1] = {
            'start_time': time.time(),
            'duration': self.cook_time_side1 if side == 1 else self.cook_time_side2,
            'side': side,
            'arepa_id': arepa_id
        }
        
        self.log_message(f"⏲️ Timer {arepa_id} - Lado {side} - P{position}")
    
    def update_timers(self):
        """Actualiza los timers visuales"""
        current_time = time.time()
        
        for i, timer_info in enumerate(self.grill_timers):
            if timer_info is None:
                self.timer_labels[i].config(text="--:--", foreground="gray")
                continue
            
            elapsed = current_time - timer_info['start_time']
            remaining = max(0, timer_info['duration'] - elapsed)
            
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            
            if remaining > 0:
                self.timer_labels[i].config(
                    text=f"{mins:02d}:{secs:02d}", 
                    foreground="red" if timer_info['side'] == 1 else "blue"
                )
            else:
                side_text = "GIRAR" if timer_info['side'] == 1 else "LISTO"
                self.timer_labels[i].config(text=side_text, foreground="green")
        
        # Programar siguiente actualización
        self.root.after(1000, self.update_timers)
    
    def update_grill_display(self):
        """Actualiza el display de la parrilla"""
        for i in range(4):
            arepa_id = self.grill_positions[i]
            if arepa_id is None:
                self.grill_labels[i].config(text="Vacío", background="lightgray")
            else:
                arepa = self.arepas[arepa_id]
                if arepa.state == ArepaState.TRANSPORTING_TO_GRILL:
                    self.grill_labels[i].config(text=f"{arepa_id}\nMoviendo", background="yellow")
                elif arepa.state == ArepaState.COOKING_SIDE1:
                    self.grill_labels[i].config(text=f"{arepa_id}\nLado 1", background="orange")
                elif arepa.state == ArepaState.FLIPPING:
                    self.grill_labels[i].config(text=f"{arepa_id}\nGirando", background="purple")
                elif arepa.state == ArepaState.COOKING_SIDE2:
                    self.grill_labels[i].config(text=f"{arepa_id}\nLado 2", background="red")
                elif arepa.state == ArepaState.TRANSPORTING_TO_DELIVERY:
                    self.grill_labels[i].config(text=f"{arepa_id}\nEntrega", background="lightblue")
                elif arepa.state == ArepaState.ERROR:
                    self.grill_labels[i].config(text=f"{arepa_id}\nERROR", background="darkred", foreground="white")
        
        self.root.update_idletasks()
    
    def update_delivery_display(self):
        """Actualiza el display de entrega - MEJORADO PARA CONFIRMACIÓN VISUAL"""
        for i in range(4):
            arepa_id = self.delivery_positions[i]
            if arepa_id is None:
                self.delivery_labels[i].config(text="Vacío", background="lightgray", foreground="black")
            else:
                # Verificar que la arepa esté realmente entregada
                arepa = self.arepas[arepa_id]
                if arepa.state == ArepaState.DELIVERED:
                    self.delivery_labels[i].config(text=f"{arepa_id}\nListo", background="lightgreen", foreground="black")
                else:
                    # Si por alguna razón el estado no coincide, mostrar en proceso
                    self.delivery_labels[i].config(text=f"{arepa_id}\nProceso", background="yellow", foreground="black")
        
        self.root.update_idletasks()
    
    def stop_process(self):
        """Detiene el proceso actual"""
        self.stop_control = True
        self.log_message("🛑 DETENIENDO...")
        self.update_status("Deteniendo...")
        
        # Esperar que termine el hilo
        if self.main_control_thread and self.main_control_thread.is_alive():
            self.main_control_thread.join(timeout=5)
        
        self.cleanup_process()
    
    def cleanup_process(self):
        """Limpia el proceso y restaura el estado"""
        self.is_executing = False
        self.stop_control = False
        
        # Habilitar botones
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        
        # Habilitar selección de arepas
        for btn in self.arepa_buttons.values():
            btn.configure(state="normal")
        
        if not self.stop_control:
            self.update_status("Proceso completado")
        else:
            self.update_status("Proceso detenido")
        
        self.log_message("Sistema listo")
    
    def go_to_home(self):
        """Mueve el robot a la posición Home"""
        if self.is_executing:
            messagebox.showwarning("Proceso activo", "No se puede mover a Home durante la ejecución")
            return
        
        self.log_message("Moviendo a Home...")
        if self.move_to_target("Home"):
            self.log_message("✓ Robot en Home")
            self.update_status("Robot en Home")
        else:
            self.log_message("✗ Error moviendo a Home")
    
    def reset_system(self):
        """Reinicia el sistema"""
        if self.is_executing:
            self.stop_process()
            time.sleep(1)
        
        # Limpiar estados
        for arepa in self.arepas.values():
            arepa.state = ArepaState.IDLE
            arepa.grill_position = None
            arepa.cook_start_time = None
            arepa.flip_time = None
            arepa.delivery_time = None
            arepa.selection_order = None
        
        # Limpiar posiciones
        self.grill_positions = [None, None, None, None]
        self.delivery_positions = [None, None, None, None]
        self.grill_timers = [None, None, None, None]
        
        # Limpiar selección
        self.selected_arepas = []
        for var in self.arepa_vars.values():
            var.set(False)
        
        # Actualizar displays
        self.update_grill_display()
        self.update_delivery_display()
        self.order_label.config(text="Selecciona hasta 4 arepas")
    
        
        self.log_message("🔄 SISTEMA REINICIADO")
        self.update_status("Sistema reiniciado - Listo")
    
    def check_robodk_connection(self):
        """Verifica la conexión con RoboDK"""
        try:
            if ROBODK_AVAILABLE:
                stations = self.RDK.getOpenStations()
                if stations:
                    self.log_message(f"✓ RoboDK OK - Estaciones: {stations}")
                    messagebox.showinfo("RoboDK", f"Conectado OK\nEstaciones: {', '.join(stations)}")
                else:
                    self.log_message("⚠️ RoboDK sin estaciones")
                    messagebox.showwarning("RoboDK", "Conectado pero sin estaciones")
            else:
                self.log_message("ℹ️ RoboDK no disponible - Simulación")
                messagebox.showinfo("RoboDK", "No disponible - Modo simulación")
                
        except Exception as e:
            error_msg = f"✗ Error RoboDK: {str(e)}"
            self.log_message(error_msg)
            messagebox.showerror("Error RoboDK", error_msg)
    
    def on_closing(self):
        """Maneja el cierre de la aplicación"""
        if self.is_executing:
            if messagebox.askokcancel("Cerrar", "¿Detener proceso y cerrar?"):
                self.stop_process()
                time.sleep(1)
                self.root.destroy()
        else:
            self.root.destroy()

def main():
    """Función principal"""
    print("=" * 40)
    print("Sistema Control Arepas - Parrilla Automática")
    print("=" * 40)
    
    root = tk.Tk()
    app = ArepaController(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nAplicación cerrada por el usuario")
    except Exception as e:
        print(f"Error en la aplicación: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
