import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'dart:io';
import 'dart:convert';
import '../models/idea_page/ImageBox.dart';
import '../models/idea_page/SegmentButton.dart';
import '../models/idea_page/PromptBar.dart';

class IdeaPage_test extends StatefulWidget {
  @override
  _IdeaPage_testState createState() => _IdeaPage_testState();
}

class _IdeaPage_testState extends State<IdeaPage_test> {
  File? _selectedImage;
  File? _receivedImage;
  File? _outputImage;
  final ImagePicker _picker = ImagePicker();
  bool _isLoading = false;
  bool _isGPTLoading = false;
  final TextEditingController _adviceController = TextEditingController();

  @override
  void initState() {
    super.initState();
  }

  Future<void> _pickImage() async {
    try {
      final XFile? image = await _picker.pickImage(source: ImageSource.gallery);
      if (image != null) {
        setState(() {
          _selectedImage = File(image.path);
          _receivedImage = null;
          _outputImage = null;
        });
      }
    } catch (e) {
      print('Image selection error: $e');
      _showSnackBar('Image selection failed');
    }
  }

  Future<void> _sendImageToBackend() async {
    if (_selectedImage == null) {
      _showSnackBar('Please select an image!');
      return;
    }

    setState(() {
      _isLoading = true;
      _receivedImage = null;
      _outputImage = null;
    });

    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('http://127.0.0.1:5000/yolo_seg'),
      );

      request.files.add(
        await http.MultipartFile.fromPath(
          'image',
          _selectedImage!.path,
        ),
      );

      print('开始发送请求到后端...');

      var response = await request.send();
      var responseString = await response.stream.bytesToString();

      print('收到响应，状态码: ${response.statusCode}');

      if (response.statusCode == 200) {
        await _handleJsonResponse(responseString);
      } else {
        setState(() {
          _isLoading = false;
        });
        _showSnackBar('Request failed: ${response.statusCode}');
      }
    } catch (e) {
      setState(() {
        _isLoading = false;
      });
      print('发送错误: $e');
      _showSnackBar('Send failed: $e');
    }
  }

  Future<void> _handleJsonResponse(String responseBody) async {
    try {
      var jsonResponse = json.decode(responseBody);

      if (jsonResponse['success'] == true) {
        if (jsonResponse['image'] != null) {
          await _handleBase64Response(jsonResponse['image']);
        } else {
          setState(() {
            _isLoading = false;
          });
          _showSnackBar('The return is missing image data!');
        }
      } else {
        setState(() {
          _isLoading = false;
        });
        String errorMsg = jsonResponse['error'] ?? 'Unknown error';
        _showSnackBar('Processing failed: $errorMsg');
      }
    } catch (e) {
      setState(() {
        _isLoading = false;
      });
      _showSnackBar('Failed to parse response: $e');
    }
  }

  Future<void> _handleBase64Response(String base64Data) async {
    try {
      String base64String = base64Data;
      if (base64Data.contains(',')) {
        base64String = base64Data.split(',').last;
      }

      var bytes = base64.decode(base64String);

      final tempDir = Directory.systemTemp;
      final file = File('${tempDir.path}/received_image_${DateTime.now().millisecondsSinceEpoch}.jpg');
      await file.writeAsBytes(bytes);

      setState(() {
        _receivedImage = file;
        _isLoading = false;
      });
      
      _showSnackBar('Image processed successfully');
    } catch (e) {
      setState(() {
        _isLoading = false;
      });
      _showSnackBar('Image processing failed: $e');
    }
  }


  // 修改后的发送GPT数据函数
  Future<void> _sendGPTData() async {
    if (_receivedImage == null) {
      _showSnackBar('Please process an image first!');
      return;
    }

    if (_adviceController.text.trim().isEmpty) {
      _showSnackBar('Please enter your background requirements!');
      return;
    }

    setState(() {
      _isGPTLoading = true;
    });

    try {
      // 读取图片文件并转换为base64
      List<int> imageBytes = await _receivedImage!.readAsBytes();
      String base64Image = base64Encode(imageBytes);

      // 准备发送的数据
      Map<String, dynamic> requestData = {
        'image': base64Image,
        'prompt': _adviceController.text.trim(),
      };

      // 发送POST请求
      var response = await http.post(
        Uri.parse('http://127.0.0.1:5000/makeGPT'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode(requestData),
      );

      print('GPT请求状态码: ${response.statusCode}');

      if (response.statusCode == 200) {
        await _handleGPTResponse(response.body);
      } else {
        setState(() {
          _isGPTLoading = false;
        });
        _showSnackBar('GPT request failed: ${response.statusCode}');
      }
    } catch (e) {
      setState(() {
        _isGPTLoading = false;
      });
      print('GPT发送错误: $e');
      _showSnackBar('Send to GPT failed: $e');
    }
  }

  Future<void> _handleGPTResponse(String responseBody) async {
    try {
      var jsonResponse = json.decode(responseBody);

      if (jsonResponse['success'] == true) {
        if (jsonResponse['image'] != null) {
          await _handleGPTImageResponse(jsonResponse['image']);
        } else {
          setState(() {
            _isGPTLoading = false;
          });
          _showSnackBar('GPT response is missing image data!');
        }
      } else {
        setState(() {
          _isGPTLoading = false;
        });
        String errorMsg = jsonResponse['error'] ?? 'Unknown error';
        _showSnackBar('GPT processing failed: $errorMsg');
      }
    } catch (e) {
      setState(() {
        _isGPTLoading = false;
      });
      _showSnackBar('Failed to parse GPT response: $e');
    }
  }

  Future<void> _handleGPTImageResponse(String base64Data) async {
    try {
      String base64String = base64Data;
      if (base64Data.contains(',')) {
        base64String = base64Data.split(',').last;
      }

      var bytes = base64.decode(base64String);

      final tempDir = Directory.systemTemp;
      final file = File('${tempDir.path}/output_image_${DateTime.now().millisecondsSinceEpoch}.jpg');
      await file.writeAsBytes(bytes);

      setState(() {
        _outputImage = file;
        _isGPTLoading = false;
      });
      
      _showSnackBar('GPT image generated successfully');
    } catch (e) {
      setState(() {
        _isGPTLoading = false;
      });
      _showSnackBar('GPT image processing failed: $e');
    }
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: Duration(seconds: 3),
      ),
    );
  }

  Widget _buildImageBox(File? image, String label, VoidCallback? onTap, bool isInput) {
    return Expanded(
      child: Container(
        margin: EdgeInsets.all(16),
        decoration: BoxDecoration(
          border: Border.all(
            color: isInput ? Colors.blue.shade300 : Colors.green.shade300,
            width: 2,
          ),
          borderRadius: BorderRadius.circular(12),
          color: Colors.grey.shade50,
        ),
        child: Column(
          children: [
            // 标题区域
            Container(
              padding: EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isInput ? Colors.blue.shade50 : Colors.green.shade50,
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(10),
                  topRight: Radius.circular(10),
                ),
              ),
              child: Center(
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: isInput ? Colors.blue.shade800 : Colors.green.shade800,
                  ),
                ),
              ),
            ),
            // 图片内容区域
            Expanded(
              child: Container(
                padding: EdgeInsets.all(8),
                child: InkWell(
                  onTap: onTap,
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    width: double.infinity,
                    height: double.infinity,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(8),
                      color: Colors.white,
                    ),
                    child: ConstrainedBox(
                      constraints: BoxConstraints(
                        maxWidth: 300,
                        maxHeight: 300,
                      ),
                      child: _buildImageContent(image, onTap, isInput),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildImageContent(File? image, VoidCallback? onTap, bool isInput) {
    if (image != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.file(
          image,
          fit: BoxFit.contain,
          width: double.infinity,
          height: double.infinity,
          errorBuilder: (context, error, stackTrace) {
            return Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.error, color: Colors.red, size: 48),
                SizedBox(height: 8),
                Text(
                  'Image failed to load',
                  style: TextStyle(color: Colors.red),
                ),
              ],
            );
          },
        ),
      );
    } else {
      return Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            isInput ? Icons.add_photo_alternate : Icons.image_search,
            size: 48,
            color: Colors.grey.shade400,
          ),
          SizedBox(height: 12),
        ],
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    // 根据是否有receivedImage决定Send to GPT按钮的颜色和可用性
    bool isGPTButtonEnabled = _receivedImage != null;
    
    return Scaffold(
      appBar: AppBar(
        leading: null,
        title: Text('Test'),
        automaticallyImplyLeading: false,
        backgroundColor: Colors.blue.shade700,
        foregroundColor: Colors.white,
      ),
      body: Column(
        children: <Widget>[
          // 顶部图片框区域
          Container(
            height: MediaQuery.of(context).size.height * 0.23,
            child: Row(
              children: [
                _buildImageBox(_selectedImage, 'Input image', _pickImage, true),
                _buildImageBox(_receivedImage, 'Mask image', null, false),
              ],
            ),
          ),

          Container(
            height: MediaQuery.of(context).size.height * 0.23,
            child: Row(
              children: [
                _buildImageBox(_outputImage, 'Output image', null, false),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                  child: _isLoading || _isGPTLoading
                      ? Column(
                          children: [
                            CircularProgressIndicator(),
                            SizedBox(height: 12),
                            Text(
                              _isGPTLoading ? 'Generating with GPT...' : 'Processing the image...',
                              style: TextStyle(
                                color: Colors.grey.shade600,
                              ),
                            ),
                          ],
                        )
                      : Column(
                          children: [
                            // Segment按钮
                            Align(
                              alignment: Alignment.centerRight,
                              child: ElevatedButton(
                                onPressed: _sendImageToBackend,
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.blue.shade600,
                                  foregroundColor: Colors.white,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(20),
                                  ),
                                  padding: EdgeInsets.symmetric(
                                    horizontal: 25,
                                    vertical: 15,
                                  ),
                                  elevation: 2,
                                  minimumSize: Size(120, 50),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      'Segment',
                                      style: TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.w600,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            SizedBox(height: 16),
                            // Send to GPT按钮 - 根据条件改变颜色
                            Align(
                              alignment: Alignment.centerRight,
                              child: ElevatedButton(
                                onPressed: isGPTButtonEnabled ? _sendGPTData : null,
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: isGPTButtonEnabled 
                                      ? Colors.green.shade600 
                                      : Colors.grey.shade400,
                                  foregroundColor: Colors.white,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(20),
                                  ),
                                  padding: EdgeInsets.symmetric(
                                    horizontal: 25,
                                    vertical: 15,
                                  ),
                                  elevation: 2,
                                  minimumSize: Size(120, 50),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      'Send to GPT',
                                      style: TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.w600,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                ),
              ],
            ),
          ),

          Expanded(
            child: Container(),
          ),
          PromptTextField(
            controller: _adviceController, // 确保传入外部控制器
            labelText: '输入您的背景需求',
            hintText: '我想要让GPT...',
            height: 70.0,
            autoFocus: true,
            maxLength: 500,
            onChanged: (text) {
              print('当前输入: $text');
            },
            textStyle: TextStyle(fontSize: 16),
          ),
        ],
      ),
    );
  }
}