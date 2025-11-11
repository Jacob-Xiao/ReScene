from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# 目标API地址
TARGET_URL = "http://localhost:11434/api/chat"


@app.route('/submit_content', methods=['POST'])
def submit_content():
    try:
        # 获取JSON数据
        data = request.get_json()

        # 检查数据是否成功接收
        if data is None:
            return jsonify({'error': 'No JSON data received'}), 400

        # 提取具体字段
        model = data.get('model')
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
        print(f"Model: {model}")
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

                # 可以根据实际响应结构提取需要的信息
                # 例如，如果响应中有'message'字段
                if 'message' in result:
                    print(f"消息内容: {result['message']}")

                # 返回给前端的响应
                return jsonify({
                    'status': 'success',
                    'message': 'Data processed successfully',
                    'received_data': {
                        'model': model,
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


if __name__ == '__main__':
    app.run(debug=True, port=5000)