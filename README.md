# 🤖 Automatización del Proceso de Preparación de Arepas

## 🌟 Resultados de Aprendizaje

Desarrollo de un sistema robotizado **simulado** para automatizar el proceso de preparación de arepas, desde la selección aleatoria en una vitrina hasta su cocción y entrega, usando herramientas como **RoboDK**, lógica de control por tareas y una interfaz HMI personalizada.

---

## 🛠️ Requisitos del Proyecto

* Simulación completa en **RoboDK**.
* Interfaz humano-máquina (HMI) en **Tkinter**.
* Lógica de selección y cocción por prioridades.
* Diseño de gripper electroneumático (modelo CAD incluido).
* Estantería (modelo BAGGEBO).
* Entrega simulada a posiciones de salida.

---

## 🍽️ Descripción del Problema

La elaboración manual de arepas en entornos industriales puede ser ineficiente, propenso a errores y riesgoso para la higiene. Este proyecto busca automatizar el proceso completo de preparación de arepas, incluyendo:

* Reducción del contacto humano.
* Cocción uniforme en ambos lados.
* Mayor eficiencia en la preparación y entrega.

---

## 🍔 Objetos Manipulados

* Arepas de distintos **tamaños, formas y prioridades**.
* Distribuidas aleatoriamente en 6 posiciones de estantería: `A1 - B3`.
* Parrilla de cocción con 4 posiciones: `1 - 4`.

---

## 🔧 Desarrollo del Gripper

Diseñado para adaptarse a distintas formas y pesos de arepas. Utiliza actuadores neumáticos con doble efecto y montaje modular en el extremo del robot.

**📸 Foto del gripper:**
`![Foto del gripper](ruta/a/la/foto.jpg)`

**📐 Modelo CAD del gripper:**
`![Modelo CAD del gripper](ruta/a/la/foto.jpg)`

**🔩 Gripper montado en el robot:**
`![Gripper en el robot](ruta/a/la/foto.jpg)`

---

## 🗃️ Alistamiento y Estructura de Trabajo

* Estantería tipo BAGGEBO con 6 arepas en posiciones aleatorias.
* Parrilla con 4 posiciones disponibles.
* Sistema de entrega automatizado con posiciones de salida.

**📸 Robot con estantería y arepas:**
`![Robot con estantería y arepas](ruta/a/la/foto.jpg)`

---

## ⚙️ Proceso Automatizado

1. Selección de arepa desde la interfaz.
2. Toma desde la estantería.
3. Posicionamiento en parrilla libre.
4. Volteo tras tiempo estimado de cocción.
5. Entrega a recipiente final.

---

## 💻 Interfaz Gráfica (HMI)

* Permite selección de hasta 4 arepas.
* Muestra estado de parrilla y entregas.
* Ajuste de velocidades y control de ejecución.

**📸 Captura de la interfaz HMI:**
`![Interfaz HMI](ruta/a/la/foto.jpg)`

---

## 🧠 Diagrama de Flujo

### Proceso Principal Completo

```mermaid
flowchart TD
    A[Inicio del Sistema] --> B["Seleccionar Arepas<br/>hasta 4 máximo"]
    B --> C{"¿Arepas<br/>seleccionadas?"}
    C -->|No| B
    C -->|Sí| D["Optimizar Orden<br/>por Prioridad"]
    D --> E[Iniciar Proceso]
    E --> F[Resetear Estados del Sistema]
    F --> G[Crear Hilos de Control]
    G --> H[Control Loop]
    G --> I[Task Monitor Loop]
    
    H --> J{"¿Hay boquillas<br/>disponibles?"}
    J -->|No| K[Esperar 1s]
    K --> J
    J -->|Sí| L[Procesar Arepa a Parrilla]
    L --> M{"¿Más arepas<br/>pendientes?"}
    M -->|Sí| J
    M -->|No| N[Esperar Completación]
    
    I --> O[Monitorear Cola de Tareas]
    O --> P{"¿Tarea lista<br/>para ejecutar?"}
    P -->|No| Q[Esperar 0.5s]
    Q --> O
    P -->|Sí| R[Ejecutar Tarea]
    R --> S[Actualizar Displays]
    S --> O
    
    N --> T{"¿Todas las arepas<br/>entregadas?"}
    T -->|No| U[Esperar 2s]
    U --> T
    T -->|Sí| V[Proceso Completado]
    V --> W[Finalizar Hilos]
    W --> X[Restaurar Interfaz]
    X --> Z[Fin]
```

### Función arepa a la estufa

```mermaid
  flowchart TD
    A["process_arepa_to_grill<br/>arepa_id"] --> B["Cambiar estado a<br/>MOVING_TO_GRILL"]
    B --> C["Asignar posición<br/>en parrilla"]
    C --> D{"¿Posición<br/>asignada?"}
    D -->|No| E[Log error]
    E --> F[Return]
    D -->|Sí| G["Marcar robot<br/>como ocupado"]
    G --> H[pickup_arepa]
    H --> I{"¿Recogida<br/>exitosa?"}
    I -->|No| J["Liberar posición<br/>parrilla"]
    J --> F
    I -->|Sí| K[place_arepa_on_grill]
    K --> L{"¿Colocación<br/>exitosa?"}
    L -->|No| J
    L -->|Sí| M["Cambiar estado a<br/>COOKING_SIDE1"]
    M --> N["Calcular tiempo<br/>de volteo"]
    N --> O[Crear tarea FLIP_AREPA]
    O --> P[Agregar tarea a cola]
    P --> Q[Marcar robot libre]
    Q --> R[Actualizar displays]
    R --> S[Return exitoso]
  
```

### Sistema de colas de Tareas

```mermaid
  flowchart TD
    A[Task Monitor Loop] --> B[Obtener tiempo actual]
    B --> C[Adquirir lock de prioridad]
    C --> D{"¿Hay tareas en cola?"}
    D -->|No| E[Liberar lock]
    E --> F[Actualizar displays]
    F --> G[Esperar 0.5s]
    G --> A
    
    D -->|Sí| H{"¿Primera tarea<br/>lista para ejecutar?"}
    H -->|No| E
    H -->|Sí| I["Extraer tarea de cola<br/>heapq.heappop"]
    I --> J[Liberar lock]
    J --> K{"¿Interrumpir tarea<br/>actual por prioridad?"}
    K -->|Sí| L["Lógica de interrupción<br/>futuro"]
    K -->|No| M[execute_task]
    L --> M
    
    M --> N{"¿Tipo de tarea?"}
    N -->|FLIP_AREPA| O[execute_flip_task]
    N -->|FINISH_COOKING| P[execute_finish_task]
    
    O --> Q[Esperar robot libre]
    Q --> R[Marcar robot ocupado]
    R --> S[flip_arepa_on_grill]
    S --> T[Cambiar a COOKING_SIDE2]
    T --> U[Crear tarea FINISH_COOKING]
    U --> V[Marcar robot libre]
    
    P --> W[Esperar robot libre]
    W --> X[Marcar robot ocupado]
    X --> Y[deliver_arepa]
    Y --> Z[Cambiar a DELIVERED]
    Z --> AA[Liberar posición parrilla]
    AA --> BB[Marcar robot libre]
    
    V --> F
    BB --> F
```

### Secuencias de movimiento del Robot

```mermaid

  flowchart TD
    A["safe_move_sequence<br/>arepa_id, sequence"] --> B["Iniciar bucle<br/>por cada frame"]
    B --> C{"¿stop_control<br/>activado?"}
    C -->|Sí| D[Return False]
    C -->|No| E["get_frame_pose<br/>frame_name"]
    E --> F{"¿Tipo de frame?"}
    
    F -->|Aprox| G["robot.MoveJ<br/>rápido"]
    F -->|Pre| H["robot.MoveL<br/>preciso"]
    F -->|Otros| I["robot.MoveJ<br/>normal"]
    
    G --> J{"¿Es último<br/>movimiento?"}
    H --> J
    I --> J
    
    J -->|No| K{"¿Tipo de espera?"}
    K -->|Aprox| L["Esperar travel*0.5"]
    K -->|Otros| M[Esperar travel]
    L --> N[Log movimiento]
    M --> N
    
    J -->|Sí| N
    N --> O{"¿Más frames<br/>en secuencia?"}
    O -->|Sí| B
    O -->|No| P[Return True]
    
    E --> Q["Error: Frame no encontrado"]
    Q --> R[Log error]
    R --> S[Return False]

```

---

## 💾 Código Fuente

> Proyecto desarrollado en Python utilizando la API de RoboDK y GUI en Tkinter.

* Estados definidos: `IDLE`, `SELECTED`, `COOKING`, `FLIPPING`, `DELIVERED`, etc.
* Manejo de tareas programadas con prioridad (heapq).
* Control seguro de movimiento entre "frames" predefinidos.
* Funciones dedicadas: `pickup_arepa()`, `flip_arepa_on_grill()`, `deliver_arepa()`.
* Optimiza el orden de procesamiento según prioridad y tiempo de cocción.

**🔗 Ver código completo:** [proyecto\_arepas.py](ruta/a/github)

---

## 🎥 Video del Proyecto

* Simulación completa en RoboDK con trayectorias.
* Explicación del funcionamiento del gripper y la interfaz.
* [🔗 Ver video](https://...)

---

## 📌 Consideraciones Finales

* Todo el desarrollo fue realizado en simulación.
* Se documenta el sistema como si estuviera listo para implementación real.
* Se priorizó la lógica modular y la adaptabilidad del sistema.

---

**Autores:** \[Nombres del equipo]
**Curso:** Robótica - 2025-I
**Universidad Nacional de Colombia**
