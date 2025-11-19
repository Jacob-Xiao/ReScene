import sys
import os
from cProfile import label
import requests
from flask import Flask, request, jsonify, send_file
import base64
from openai import OpenAI
from datetime import datetime
import tempfile
from dotenv import load_dotenv

# --- 新增依赖 ---
import json
import mysql.connector
from mysql.connector import pooling

# 添加正确的 ultralytics 路径到 Python 路径
correct_ultralytics_path = 'C:/Users/30583/Desktop/PY/ultralytics-main'
sys.path.insert(0, correct_ultralytics_path)

# 移除可能冲突的路径
conflicting_paths = [p for p in sys.path if 'yolov8-main' in p]
for path in conflicting_paths:
    sys.path.remove(path)

print("当前Python路径:")
for path in sys.path[:3]:  # 只显示前3个
    print(f"  - {path}")

from flask_cors import CORS
from ultralytics import YOLO
import cv2
import numpy as np
import io
from PIL import Image
import time
import torch

app = Flask(__name__)
CORS(app)  # 允许跨域请求

TARGET_URL = "http://localhost:11434/api/chat"
print("LlamaAPI  ", TARGET_URL)

print("正在加载YOLOv11模型...")
# 加载预训练的 YOLOv11 模型
model = YOLO('C:/Users/30583/Desktop/PY/ultralytics-main/lib/runs/yolo11x-seg.pt')
print("模型加载成功!")
print(f"模型类别: {model.names}")

# 创建保存结果的目录
os.makedirs('uploads', exist_ok=True)
os.makedirs('results', exist_ok=True)

# 加载 env（保留你原来的路径）
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "C:/Users/30583/Desktop/API/.env"))
# 初始化OpenAI客户端
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)

# ---------------- MySQL 配置（使用你给的凭据） ----------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "charset": os.getenv("DB_CHARSET", "utf8mb4"),
}


# 我们会在启动时确保数据库与表存在
def ensure_database_and_tables():
    try:
        # 先连接到 MySQL（不指定数据库），以便创建数据库（如果不存在）
        tmp_conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            charset=DB_CONFIG.get('charset', 'utf8mb4'),
            use_unicode=True
        )
        tmp_cursor = tmp_conn.cursor()
        tmp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;")
        tmp_conn.commit()
        tmp_cursor.close()
        tmp_conn.close()
    except Exception as e:
        print(f"[DB Init] 创建数据库失败: {e}")
        raise

    # 现在创建连接池（会在模块全局中赋值）
    global connection_pool
    try:
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="mypool",
            pool_size=5,
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            charset=DB_CONFIG.get('charset', 'utf8mb4'),
            use_unicode=True
        )
    except Exception as e:
        print(f"[DB Init] 创建连接池失败: {e}")
        raise

    # 创建表
    try:
        conn = connection_pool.get_connection()
        cursor = conn.cursor()
        create_gpt_table = """
        CREATE TABLE IF NOT EXISTS gpt_image_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            prompt TEXT,
            user_image_longtext LONGTEXT,
            output_image_longtext LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET = utf8mb4;
        """
        create_yolo_table = """
        CREATE TABLE IF NOT EXISTS yolo_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            object_count INT,
            detections JSON,
            input_image_longtext LONGTEXT,
            segmented_image_longtext LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET = utf8mb4;
        """
        cursor.execute(create_gpt_table)
        cursor.execute(create_yolo_table)
        conn.commit()
        cursor.close()
        conn.close()
        print("[DB Init] 数据库与表已确认存在。")
    except Exception as e:
        print(f"[DB Init] 创建表失败: {e}")
        raise

# 立即确保数据库与表
ensure_database_and_tables()

# ----------------- 数据库写入函数 -----------------
def insert_gpt_log(prompt, user_img_b64, output_img_b64):
    try:
        conn = connection_pool.get_connection()
        cursor = conn.cursor()
        sql = """
        INSERT INTO gpt_image_logs (prompt, user_image_longtext, output_image_longtext)
        VALUES (%s, %s, %s)
        """
        cursor.execute(sql, (prompt, user_img_b64, output_img_b64))
        conn.commit()
    except Exception as e:
        print(f"[DB] insert_gpt_log 失败: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

def insert_yolo_log(object_count, detections, input_img_b64, segmented_img_b64):
    try:
        conn = connection_pool.get_connection()
        cursor = conn.cursor()
        sql = """
        INSERT INTO yolo_logs (object_count, detections, input_image_longtext, segmented_image_longtext)
        VALUES (%s, %s, %s, %s)
        """
        # detections 存为 JSON 字符串
        det_json = json.dumps(detections, ensure_ascii=False)
        cursor.execute(sql, (object_count, det_json, input_img_b64, segmented_img_b64))
        conn.commit()
    except Exception as e:
        print(f"[DB] insert_yolo_log 失败: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

# ----------------- 你的图像处理函数（保持不变，仅进行了小修正） -----------------
def process_image_segmentation_only(image_data):
    """
    处理上传的图片并进行YOLO推理，只返回分割后的透明背景图像
    """
    try:
        # 将图片数据转换为OpenCV格式
        if isinstance(image_data, str):
            # 如果是base64字符串
            if image_data.startswith('data:'):
                image_data = base64.b64decode(image_data.split(',')[-1])
            else:
                image_data = base64.b64decode(image_data)

        nparr = np.frombuffer(image_data, np.uint8)
        orig_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if orig_img is None:
            raise ValueError("无法解码图片")

        print(f"开始推理，图片尺寸: {orig_img.shape}")

        # 运行YOLO推理
        results = model.predict(orig_img, save=False, conf=0.25, iou=0.45, verbose=False)

        # 获取第一个结果（单张图片）
        result = results[0]

        # 创建分割后的透明背景图像
        if result.masks is not None:
            masks = result.masks.data.cpu().numpy()

            # 创建合并后的二值掩码（所有目标合并）
            combined_mask = np.zeros((orig_img.shape[0], orig_img.shape[1]), dtype=np.uint8)

            # 合并所有掩码
            for j, mask in enumerate(masks):
                # 调整掩码尺寸
                mask_resized = cv2.resize(mask, (orig_img.shape[1], orig_img.shape[0]))
                binary_mask = (mask_resized > 0.5).astype(np.uint8)
                # 合并到总掩码中
                combined_mask = np.maximum(combined_mask, binary_mask)

            # 将BGR转换为RGB
            rgb_img = cv2.cvtColor(orig_img, cv2.COLOR_BGR2RGB)

            # 创建RGBA图像
            rgba_array = np.zeros((*rgb_img.shape[:2], 4), dtype=np.uint8)
            rgba_array[..., :3] = rgb_img  # RGB通道
            rgba_array[..., 3] = combined_mask * 255  # Alpha通道

            # 使用PIL保存，确保透明度正确
            segmented_img = Image.fromarray(rgba_array, 'RGBA')

            print(f"检测到 {len(masks)} 个目标，已合并到一张透明背景图中")
        else:
            # 如果没有检测到任何目标，创建完全透明的图像
            rgb_img = cv2.cvtColor(orig_img, cv2.COLOR_BGR2RGB)
            rgba_array = np.zeros((*rgb_img.shape[:2], 4), dtype=np.uint8)
            segmented_img = Image.fromarray(rgba_array, 'RGBA')
            print("未检测到任何目标")

        # 获取检测信息
        detection_info = []
        if hasattr(result, 'boxes') and result.boxes is not None:
            boxes = result.boxes
            for i in range(len(boxes)):
                box = boxes[i]
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].tolist()

                detection_info.append({
                    'class': cls,
                    'class_name': model.names[cls],
                    'confidence': round(conf, 4),
                    'bbox': [round(x, 2) for x in xyxy]
                })

        print(f"分割处理完成，检测到 {len(detection_info)} 个目标")

        return {
            'success': True,
            'segmented_image': segmented_img,
            'detections': detection_info,
            'original_shape': orig_img.shape,
            'has_segmentation': result.masks is not None,
            'object_count': len(masks) if result.masks is not None else 0
        }

    except Exception as e:
        print(f"处理图片时出错: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def process_image_original(image_data):
    """
    原始的处理函数，返回带标注的完整图像
    """
    try:
        # 将图片数据转换为OpenCV格式
        if isinstance(image_data, str):
            # 如果是base64字符串
            if image_data.startswith('data:'):
                image_data = base64.b64decode(image_data.split(',')[-1])
            else:
                image_data = base64.b64decode(image_data)

        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("无法解码图片")

        print(f"开始推理，图片尺寸: {img.shape}")

        # 运行YOLO推理
        results = model.predict(img, save=False, conf=0.25, iou=0.45, verbose=False)

        # 获取第一个结果（单张图片）
        result = results[0]

        # 绘制结果
        annotated_img = result.plot()  # 这个会自动绘制检测框和分割掩码

        # 转换为BGR到RGB（用于PIL）
        annotated_img_rgb = cv2.cvtColor(annotated_img, cv2.COLOR_BGR2RGB)

        # 转换为PIL Image
        pil_img = Image.fromarray(annotated_img_rgb)

        # 获取检测信息
        detection_info = []
        if hasattr(result, 'boxes') and result.boxes is not None:
            boxes = result.boxes
            for i in range(len(boxes)):
                box = boxes[i]
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].tolist()

                detection_info.append({
                    'class': cls,
                    'class_name': model.names[cls],
                    'confidence': round(conf, 4),
                    'bbox': [round(x, 2) for x in xyxy]
                })

        print(f"推理完成，检测到 {len(detection_info)} 个目标")

        return {
            'success': True,
            'annotated_image': pil_img,
            'detections': detection_info,
            'original_shape': img.shape,
            'processed_shape': annotated_img.shape
        }

    except Exception as e:
        print(f"处理图片时出错: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def base64_to_temp_file(image_base64):
    """将base64转换为临时文件路径"""
    # 去除可能的数据URL前缀
    if ',' in image_base64:
        image_base64 = image_base64.split(',')[1]

    # 解码并创建临时文件
    image_data = base64.b64decode(image_base64)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    temp_file_path = temp_file.name
    temp_file.write(image_data)
    temp_file.close()

    return temp_file_path

# ----------------- API: /yolo_seg -----------------
@app.route('/yolo_seg', methods=['POST'])
def yolo_segmentation_transparent():
    """
    YOLO图像分割API端点 - 只返回分割后的透明背景图像
    """
    start_time = time.time()

    try:
        # 检查是否有文件上传
        if 'image' not in request.files and ('image' not in request.json or not request.json):
            return jsonify({
                'success': False,
                'error': '没有收到图片文件'
            }), 400

        image_data = None

        # 处理文件上传
        if 'image' in request.files:
            file = request.files['image']
            if file.filename == '':
                return jsonify({
                    'success': False,
                    'error': '没有选择文件'
                }), 400

            image_data = file.read()
            print(f"收到文件上传: {file.filename}, 大小: {len(image_data)} 字节")

        # 处理base64编码的图片
        elif request.json and 'image' in request.json:
            image_data = request.json['image']
            print(f"收到Base64图片，数据长度: {len(image_data)}")

        if not image_data:
            return jsonify({
                'success': False,
                'error': '图片数据为空'
            }), 400

        # 处理图片 - 使用新的分割函数
        result = process_image_segmentation_only(image_data)

        if not result['success']:
            return jsonify(result), 500

        # 将处理后的透明图片转换为base64
        img_byte_arr = io.BytesIO()
        result['segmented_image'].save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        base64_image = base64.b64encode(img_byte_arr).decode('utf-8')

        processing_time = round(time.time() - start_time, 2)

        response_data = {
            'success': True,
            'message': '分割完成',
            'image': f"data:image/png;base64,{base64_image}",
            'detections': result['detections'],
            'original_shape': result['original_shape'],
            'has_segmentation': result['has_segmentation'],
            'object_count': result['object_count'],
            'processing_time': processing_time,
            'timestamp': time.time(),
            'image_type': 'transparent_png'
        }

        # --- 写入数据库 ---
        try:
            # 规范化 input image 为 base64 字符串，便于存储
            if isinstance(image_data, bytes):
                input_b64 = base64.b64encode(image_data).decode('utf-8')
            else:
                # 可能已经是 data:image/... 前缀或纯 b64
                if isinstance(image_data, str) and image_data.startswith('data:'):
                    input_b64 = image_data.split(',', 1)[1]
                else:
                    input_b64 = image_data if isinstance(image_data, str) else base64.b64encode(image_data).decode('utf-8')

            insert_yolo_log(
                object_count=result['object_count'],
                detections=result['detections'],
                input_img_b64=input_b64,
                segmented_img_b64=base64_image
            )
            print("[DB] YOLO 记录已写入")
        except Exception as e:
            print(f"[DB] 写入 YOLO 记录出错: {e}")

        print(f"透明分割请求处理完成，耗时: {processing_time}秒")
        return jsonify(response_data)

    except Exception as e:
        error_time = round(time.time() - start_time, 2)
        print(f"处理请求时出错，耗时: {error_time}秒, 错误: {e}")
        return jsonify({
            'success': False,
            'error': f'处理过程中发生错误: {str(e)}',
            'processing_time': error_time
        }), 500

# ----------------- 其他 API 保持不变 -----------------
@app.route('/get_image/<filename>', methods=['GET'])
def get_image(filename):
    """
    获取处理后的图片文件
    """
    try:
        # 安全检查，防止路径遍历攻击
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': '无效的文件名'}), 400

        return send_file(f'results/{filename}', mimetype='image/jpeg')
    except FileNotFoundError:
        return jsonify({'error': '图片未找到'}), 404

@app.route('/health', methods=['GET'])
def health_check():
    """
    健康检查端点
    """
    return jsonify({
        'status': 'healthy',
        'model_loaded': model is not None,
        'model_classes': len(model.names) if model else 0,
        'timestamp': time.time()
    })

@app.route('/model_info', methods=['GET'])
def model_info():
    """
    获取模型信息
    """
    try:
        return jsonify({
            'model_name': 'YOLOv11-seg',
            'classes': model.names,
            'class_count': len(model.names),
            'success': True
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 错误处理
@app.errorhandler(413)
def too_large(e):
    return jsonify({
        'success': False,
        'error': '文件太大'
    }), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({
        'success': False,
        'error': '内部服务器错误'
    }), 500

@app.route('/submit_content', methods=['POST'])
def submit_content():
    try:
        # 获取JSON数据
        data = request.get_json()

        # 检查数据是否成功接收
        if data is None:
            return jsonify({'error': 'No JSON data received'}), 400

        # 提取具体字段
        model_field = data.get('model')
        messages = data.get('messages', [])
        stream = data.get('stream', False)

        # 提取消息内容
        user_message = ""
        role = ""
        if messages and len(messages) > 0:
            user_message = messages[0].get('content', '')
            role = messages[0].get('role', '')

        # 打印接收到的数据（调试用）
        print("=== 接收到的原始数据 ===")
        print(f"Model: {model_field}")
        print(f"Messages: {messages}")
        print(f"Stream: {stream}")
        print(f"User Message: {user_message}")
        print(f"Role: {role}")

        # 转发数据到目标API
        print("\n=== 开始转发数据到目标API ===")
        print(f"目标URL: {TARGET_URL}")

        try:
            # 发送POST请求到目标API
            response = requests.post(TARGET_URL, json=data)

            # 检查响应状态
            print(f"响应状态码: {response.status_code}")

            if response.status_code == 200:
                # 成功获取响应
                result = response.json()
                print("\n=== 目标API返回的数据 ===")
                print(f"完整响应: {result}")

                # 返回给前端的响应
                return jsonify({
                    'status': 'success',
                    'message': 'Data processed successfully',
                    'received_data': {
                        'model': model_field,
                        'user_message': user_message,
                        'role': role,
                        'stream': stream
                    },
                    'api_response': result  # 包含目标API的响应
                }), 200
            else:
                # 目标API返回错误
                print(f"目标API错误: {response.status_code} - {response.text}")
                return jsonify({
                    'status': 'error',
                    'message': f'Target API returned error: {response.status_code}',
                    'error_details': response.text
                }), response.status_code

        except requests.exceptions.ConnectionError:
            print("无法连接到目标API，请检查服务是否启动")
            return jsonify({
                'status': 'error',
                'message': 'Cannot connect to target API. Please check if the service is running.'
            }), 503
        except requests.exceptions.Timeout:
            print("连接目标API超时")
            return jsonify({
                'status': 'error',
                'message': 'Connection to target API timed out.'
            }), 504
        except Exception as api_error:
            print(f"调用目标API时发生错误: {str(api_error)}")
            return jsonify({
                'status': 'error',
                'message': f'Error calling target API: {str(api_error)}'
            }), 500

    except Exception as e:
        print(f"处理请求时发生错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ----------------- /makeGPT: 图像编辑并写入 DB -----------------
@app.route('/makeGPT', methods=['POST'])
def make_gpt():
    temp_file_path = None  # 初始化变量，便于 finally 中判断

    try:
        # 获取JSON数据
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'error': 'No JSON数据接收'}), 400

        # 获取图片base64数据和提示词
        image_base64 = data.get('image')
        prompt = data.get('prompt')

        if not image_base64:
            return jsonify({'success': False, 'error': '没有接收到图片数据'}), 400

        if not prompt:
            return jsonify({'success': False, 'error': '没有接收到提示词'}), 400

        print(f"接收到的提示词: {prompt}")
        print(f"接收到的图片数据长度: {len(image_base64)}")

        temp_file_path = base64_to_temp_file(image_base64)

        # 调用OpenAI API进行图像编辑
        response = client.images.edit(
            model="gpt-image-1",
            image=open(temp_file_path, "rb"),
            prompt=prompt,
            size="1024x1024",
        )

        print("GPT API调用成功")

        # 正确解析ImagesResponse对象
        if hasattr(response, 'data') and len(response.data) > 0:
            # 直接从响应中获取base64图像数据
            image_base64_out = response.data[0].b64_json

            print("成功获取生成的图像base64数据")

            # --- 写入数据库（尽量先写入，写库失败不阻止返回） ---
            try:
                # 保证存入数据库的 user image 是纯 base64（不含 data: 前缀）
                if isinstance(image_base64, str) and image_base64.startswith('data:'):
                    store_user_b64 = image_base64.split(',', 1)[1]
                else:
                    store_user_b64 = image_base64

                insert_gpt_log(
                    prompt=prompt,
                    user_img_b64=store_user_b64,
                    output_img_b64=image_base64_out
                )
                print("[DB] GPT 记录已写入")
            except Exception as e:
                print(f"[DB] 写入 GPT 记录失败: {e}")

            # 返回图片数据给前端
            return jsonify({
                'success': True,
                'image': image_base64_out
            })
        else:
            print("API响应中没有图像数据")
            return jsonify({
                'success': False,
                'error': 'API响应中没有图像数据'
            }), 500

    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'处理失败: {str(e)}'
        }), 500
    finally:
        # 清理临时文件
        try:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        except Exception as e:
            print(f"删除临时文件失败: {e}")

# ----------------- 启动服务器 -----------------
if __name__ == '__main__':
    print("启动YOLOv11 Flask服务器...")
    print("=" * 50)
    print("模型信息:")
    print(f"- 类别数量: {len(model.names)}")
    print(f"- 前5个类别: {list(model.names.items())[:5]}")
    print("\nAPI端点:")
    print("- POST /yolo_seg: YOLO图像分割（带标注的完整图像）")
    print("- POST /yolo_seg_transparent: YOLO图像分割（只返回分割后的透明背景图像）")
    print("- GET /health: 健康检查")
    print("- GET /model_info: 模型信息")
    print("- GET /get_image/<filename>: 获取结果图片")
    print("=" * 50)
    print("服务器运行在: http://127.0.0.1:5000")

    # 设置文件大小限制为16MB
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    app.run(host='127.0.0.1', port=5000, debug=False)
