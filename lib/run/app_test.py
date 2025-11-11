import sys
import os
from cProfile import label

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

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from ultralytics import YOLO
import cv2
import numpy as np
import io
import base64
import os
from PIL import Image
import time
import torch

app = Flask(__name__)
CORS(app)  # 允许跨域请求

print("正在加载YOLOv11模型...")
# 加载预训练的 YOLOv11 模型
model = YOLO('C:/Users/30583/Desktop/PY/ultralytics-main/lib/runs/yolo11x-seg.pt')
print("模型加载成功!")
print(f"模型类别: {model.names}")

# 创建保存结果的目录
os.makedirs('uploads', exist_ok=True)
os.makedirs('results', exist_ok=True)


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

        # 保存结果图片
        timestamp = int(time.time())
        result_path = f'results/segmented_only_{timestamp}.png'
        segmented_img.save(result_path, 'PNG')

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
            'result_path': result_path,
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

        # 保存结果图片
        timestamp = int(time.time())
        result_path = f'results/result_{timestamp}.jpg'
        pil_img.save(result_path, quality=95)

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
            'result_path': result_path,
            'original_shape': img.shape,
            'processed_shape': annotated_img.shape
        }

    except Exception as e:
        print(f"处理图片时出错: {e}")
        return {
            'success': False,
            'error': str(e)
        }


# @app.route('/yolo_seg1', methods=['POST'])
# def yolo_segmentation():
#     """
#     YOLO图像分割API端点 - 返回带标注的完整图像
#     """
#     start_time = time.time()
#
#     try:
#         # 检查是否有文件上传
#         if 'image' not in request.files and ('image' not in request.json or not request.json):
#             return jsonify({
#                 'success': False,
#                 'error': '没有收到图片文件'
#             }), 400
#
#         image_data = None
#
#         # 处理文件上传
#         if 'image' in request.files:
#             file = request.files['image']
#             if file.filename == '':
#                 return jsonify({
#                     'success': False,
#                     'error': '没有选择文件'
#                 }), 400
#
#             image_data = file.read()
#             print(f"收到文件上传: {file.filename}, 大小: {len(image_data)} 字节")
#
#         # 处理base64编码的图片
#         elif request.json and 'image' in request.json:
#             image_data = request.json['image']
#             print(f"收到Base64图片，数据长度: {len(image_data)}")
#
#         if not image_data:
#             return jsonify({
#                 'success': False,
#                 'error': '图片数据为空'
#             }), 400
#
#         # 处理图片
#         result = process_image_original(image_data)
#
#         if not result['success']:
#             return jsonify(result), 500
#
#         # 将处理后的图片转换为base64
#         img_byte_arr = io.BytesIO()
#         result['annotated_image'].save(img_byte_arr, format='JPEG', quality=95)
#         img_byte_arr = img_byte_arr.getvalue()
#
#         base64_image = base64.b64encode(img_byte_arr).decode('utf-8')
#
#         processing_time = round(time.time() - start_time, 2)
#
#         response_data = {
#             'success': True,
#             'message': '推理完成',
#             'image': f"data:image/jpeg;base64,{base64_image}",
#             'detections': result['detections'],
#             'result_path': result['result_path'],
#             'original_shape': result['original_shape'],
#             'processed_shape': result['processed_shape'],
#             'processing_time': processing_time,
#             'timestamp': time.time()
#         }
#
#         print(f"请求处理完成，耗时: {processing_time}秒")
#         return jsonify(response_data)
#
#     except Exception as e:
#         error_time = round(time.time() - start_time, 2)
#         print(f"处理请求时出错，耗时: {error_time}秒, 错误: {e}")
#         return jsonify({
#             'success': False,
#             'error': f'处理过程中发生错误: {str(e)}',
#             'processing_time': error_time
#         }), 500


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
            'result_path': result['result_path'],
            'original_shape': result['original_shape'],
            'has_segmentation': result['has_segmentation'],
            'object_count': result['object_count'],
            'processing_time': processing_time,
            'timestamp': time.time(),
            'image_type': 'transparent_png'
        }

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