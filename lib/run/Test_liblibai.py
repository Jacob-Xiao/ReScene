import hmac
from hashlib import sha1
import base64
import time
import uuid
import requests
import os


def make_sign(secret_key, uri, timestamp, signature_nonce):
    """
    生成签名
    """
    # 拼接请求数据
    content = '&'.join((uri, timestamp, signature_nonce))

    # 生成签名
    digest = hmac.new(secret_key.encode(), content.encode(), sha1).digest()
    # 移除为了补全base64位数而填充的尾部等号
    sign = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
    return sign


def call_liblibai_api_with_image(access_key, secret_key, api_endpoint, image_path, prompt, output_path, params=None):
    """
    调用liblibai API上传图片和prompt，并保存返回的图片
    """
    # 基础信息
    base_url = "https://openapi.liblibai.cloud"
    uri = api_endpoint

    # 生成必要参数
    timestamp = str(int(time.time() * 1000))
    signature_nonce = str(uuid.uuid4())

    # 生成签名
    signature = make_sign(secret_key, uri, timestamp, signature_nonce)

    # 构建请求URL
    url = f"{base_url}{api_endpoint}"

    # 构建查询参数（签名相关参数）
    query_params = {
        "AccessKey": access_key,
        "Signature": signature,
        "Timestamp": timestamp,
        "SignatureNonce": signature_nonce
    }

    # 如果有其他参数，合并进去
    if params:
        query_params.update(params)

    # 检查图片文件是否存在
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    # 准备上传的文件和数据
    files = {
        'image': (os.path.basename(image_path), open(image_path, 'rb'), 'image/jpeg')
    }

    data = {
        'prompt': prompt
    }

    try:
        # 发送POST请求（multipart/form-data）
        response = requests.post(url, params=query_params, files=files, data=data)

        if response.status_code == 200:
            # 检查响应内容类型
            content_type = response.headers.get('content-type', '')

            if 'image' in content_type:
                # 保存图片
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                print(f"图片已保存至: {output_path}")
                return True
            else:
                # 如果不是图片，可能是错误信息
                print("响应不是图片，可能是错误信息:")
                print(response.text)
                return False
        else:
            print(f"请求失败，状态码: {response.status_code}")
            print("错误信息:", response.text)
            return False

    except Exception as e:
        print(f"请求异常: {e}")
        return False
    finally:
        # 确保文件被关闭
        if 'files' in locals():
            files['image'][1].close()


# 更通用的版本，支持更多参数
def call_liblibai_api_advanced(access_key, secret_key, api_endpoint, files_data=None, form_data=None, output_path=None,
                               params=None):
    """
    高级版本的API调用，支持更多参数
    """
    # 基础信息
    base_url = "https://openapi.liblibai.cloud"
    uri = api_endpoint

    # 生成必要参数
    timestamp = str(int(time.time() * 1000))
    signature_nonce = str(uuid.uuid4())

    # 生成签名
    signature = make_sign(secret_key, uri, timestamp, signature_nonce)

    # 构建请求URL
    url = f"{base_url}{api_endpoint}"

    # 构建查询参数（签名相关参数）
    query_params = {
        "AccessKey": access_key,
        "Signature": signature,
        "Timestamp": timestamp,
        "SignatureNonce": signature_nonce
    }

    # 如果有其他参数，合并进去
    if params:
        query_params.update(params)

    try:
        # 发送POST请求
        if files_data:
            # 如果有文件，使用multipart/form-data
            response = requests.post(url, params=query_params, files=files_data, data=form_data)
        else:
            # 如果没有文件，使用application/json
            response = requests.post(url, params=query_params, json=form_data)

        if response.status_code == 200:
            # 如果指定了输出路径，尝试保存图片
            if output_path:
                content_type = response.headers.get('content-type', '')
                if 'image' in content_type:
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    print(f"图片已保存至: {output_path}")
                    return True
                else:
                    # 如果不是图片，保存响应内容
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    print(f"响应内容已保存至: {output_path}")
                    return True
            else:
                # 不保存文件，直接返回响应
                return response
        else:
            print(f"请求失败，状态码: {response.status_code}")
            print("错误信息:", response.text)
            return False

    except Exception as e:
        print(f"请求异常: {e}")
        return False


# 使用示例
if __name__ == "__main__":
    # 你的认证信息
    ACCESS_KEY = "No8s9V0YkxqT_PUAobJaPA"  # 替换为你的AccessKey
    SECRET_KEY = "79Ne01AlmjGiEOhYiOKP5uRoSuwwK1KC"  # 替换为你的SecretKey
    API_ENDPOINT = "/api/genImg"  # 根据实际API端点调整

    # 配置参数
    IMAGE_PATH = "C:/Users/30583/Desktop/PY/ultralytics-main/lib/Implement/runs/segment/Test/combined_segmented_0.png"  # 替换为你的本地图片路径
    PROMPT = "guys sitting in the White House"  # 你的提示词
    OUTPUT_PATH = "C:/Users/30583/Desktop/PY/ultralytics-main/Datasets/Testoutput.png"  # 输出图片路径

    # 方法1：使用简单的图片上传函数
    print("方法1：上传图片和prompt...")
    success = call_liblibai_api_with_image(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        api_endpoint=API_ENDPOINT,
        image_path=IMAGE_PATH,
        prompt=PROMPT,
        output_path=OUTPUT_PATH
    )

    if success:
        print("图片生成成功！")
    else:
        print("图片生成失败！")

    # 方法2：使用高级版本（更灵活）
    print("\n方法2：使用高级版本...")

    # 准备文件和数据
    files_data = {
        'image': ('input.jpg', open(IMAGE_PATH, 'rb'), 'image/jpeg')
    }

    form_data = {
        'prompt': PROMPT,
        # 可以添加其他参数，根据API文档
        # 'width': 512,
        # 'height': 512,
        # 'steps': 20
    }

    success = call_liblibai_api_advanced(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        api_endpoint=API_ENDPOINT,
        files_data=files_data,
        form_data=form_data,
        output_path="output_advanced.jpg"
    )

    # 关闭文件
    files_data['image'][1].close()