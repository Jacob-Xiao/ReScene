import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

import '../const.dart';
import '../models/idea_page/prompt_bar.dart';

class IdeaPage extends StatefulWidget {
  const IdeaPage({super.key});

  @override
  State<IdeaPage> createState() => _IdeaPageState();
}

class _IdeaPageState extends State<IdeaPage> {
  File? _selectedImage;
  File? _receivedImage;
  File? _outputImage;
  final ImagePicker _picker = ImagePicker();
  bool _isLoading = false;
  bool _isGPTLoading = false;
  final TextEditingController _adviceController = TextEditingController();

  @override
  void dispose() {
    _adviceController.dispose();
    super.dispose();
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 3)),
    );
  }

  Future<void> _pickImage() async {
    try {
      final XFile? image = await _picker.pickImage(source: ImageSource.gallery);
      if (image != null && mounted) {
        setState(() {
          _selectedImage = File(image.path);
          _receivedImage = null;
          _outputImage = null;
        });
      }
    } catch (e) {
      if (!mounted) return;
      _showSnackBar('Image selection failed');
      debugPrint('Image selection error: $e');
    }
  }

  Future<void> _sendImageToBackend() async {
    if (_isLoading) return; // double-tap guard
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
        Uri.parse(ApiConfig.yoloSegUrl),
      );

      request.files.add(
        await http.MultipartFile.fromPath('image', _selectedImage!.path),
      );

      var response = await request.send().timeout(ApiConfig.requestTimeout);
      var responseString = await response.stream.bytesToString();

      if (!mounted) return;

      if (response.statusCode == 200) {
        await _handleJsonResponse(responseString);
      } else {
        setState(() => _isLoading = false);
        _showSnackBar('Request failed: ${response.statusCode}');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      debugPrint('Send error: $e');
      _showSnackBar('Send failed: $e');
    }
  }

  Future<void> _handleJsonResponse(String responseBody) async {
    try {
      var jsonResponse = json.decode(responseBody);

      if (jsonResponse['success'] == true) {
        if (jsonResponse['image'] != null) {
          await _saveImageFromBase64(
            jsonResponse['image'] as String,
            'received_image',
            onDone: (file) => _receivedImage = file,
          );
        } else {
          setState(() => _isLoading = false);
          _showSnackBar('The return is missing image data!');
        }
      } else {
        setState(() => _isLoading = false);
        String errorMsg = jsonResponse['error'] ?? 'Unknown error';
        _showSnackBar('Processing failed: $errorMsg');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      _showSnackBar('Failed to parse response: $e');
    }
  }

  /// Both endpoints return transparent PNG payloads.
  Future<void> _saveImageFromBase64(
    String base64Data,
    String filePrefix, {
    required ValueChanged<File> onDone,
  }) async {
    try {
      String base64String = base64Data.contains(',')
          ? base64Data.split(',').last
          : base64Data;

      var bytes = base64.decode(base64String);

      final tempDir = Directory.systemTemp;
      final file = File(
        '${tempDir.path}/${filePrefix}_${DateTime.now().millisecondsSinceEpoch}.png',
      );
      await file.writeAsBytes(bytes);

      if (!mounted) return;
      setState(() {
        onDone(file);
        _isLoading = false;
        _isGPTLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _isGPTLoading = false;
      });
      _showSnackBar('Image processing failed: $e');
    }
  }

  Future<void> _sendGPTData() async {
    if (_isGPTLoading) return; // double-tap guard
    if (_receivedImage == null) {
      _showSnackBar('Please process an image first!');
      return;
    }

    if (_adviceController.text.trim().isEmpty) {
      _showSnackBar('Please enter your background requirements!');
      return;
    }

    setState(() => _isGPTLoading = true);

    try {
      List<int> imageBytes = await _receivedImage!.readAsBytes();
      String base64Image = base64Encode(imageBytes);

      Map<String, dynamic> requestData = {
        'image': base64Image,
        'prompt': _adviceController.text.trim(),
      };

      var response = await http
          .post(
            Uri.parse(ApiConfig.makeGptUrl),
            headers: {'Content-Type': 'application/json'},
            body: json.encode(requestData),
          )
          .timeout(ApiConfig.gptTimeout);

      if (!mounted) return;

      if (response.statusCode == 200) {
        await _handleGPTResponse(response.body);
      } else {
        setState(() => _isGPTLoading = false);
        _showSnackBar('GPT request failed: ${response.statusCode}');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isGPTLoading = false);
      debugPrint('GPT send error: $e');
      _showSnackBar('Send to GPT failed: $e');
    }
  }

  Future<void> _handleGPTResponse(String responseBody) async {
    try {
      var jsonResponse = json.decode(responseBody);

      if (jsonResponse['success'] == true) {
        if (jsonResponse['image'] != null) {
          await _saveImageFromBase64(
            jsonResponse['image'] as String,
            'output_image',
            onDone: (file) => _outputImage = file,
          );
        } else {
          setState(() => _isGPTLoading = false);
          _showSnackBar('GPT response is missing image data!');
        }
      } else {
        setState(() => _isGPTLoading = false);
        String errorMsg = jsonResponse['error'] ?? 'Unknown error';
        _showSnackBar('GPT processing failed: $errorMsg');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isGPTLoading = false);
      _showSnackBar('Failed to parse GPT response: $e');
    }
  }

  Widget _buildImageBox(
    File? image,
    String label,
    VoidCallback? onTap,
    bool isInput,
  ) {
    return Expanded(
      child: Container(
        margin: const EdgeInsets.all(16),
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
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isInput ? Colors.blue.shade50 : Colors.green.shade50,
                borderRadius: const BorderRadius.only(
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
                    color: isInput
                        ? Colors.blue.shade800
                        : Colors.green.shade800,
                  ),
                ),
              ),
            ),
            // 图片内容区域
            Expanded(
              child: Container(
                padding: const EdgeInsets.all(8),
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
                      constraints: const BoxConstraints(
                        maxWidth: 300,
                        maxHeight: 300,
                      ),
                      child: _buildImageContent(image, isInput),
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

  Widget _buildImageContent(File? image, bool isInput) {
    if (image != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.file(
          image,
          fit: BoxFit.contain,
          width: double.infinity,
          height: double.infinity,
          errorBuilder: (context, error, stackTrace) {
            return Center(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error, color: Colors.red, size: 48),
                    const SizedBox(height: 8),
                    Text(
                      'Image failed to load',
                      style: TextStyle(color: Colors.red),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      );
    } else {
      return Center(
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Icon(
            isInput ? Icons.add_photo_alternate : Icons.image_search,
            size: 48,
            color: Colors.grey.shade400,
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    // 根据是否有receivedImage决定Send to GPT按钮的颜色和可用性
    final bool isGPTButtonEnabled = _receivedImage != null && !_isGPTLoading;

    return Scaffold(
      appBar: AppBar(
        leading: null,
        title: const Text('Idea'),
        automaticallyImplyLeading: false,
      ),
      body: Column(
        children: <Widget>[
          // 顶部图片框区域
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.23,
            child: Row(
              children: [
                _buildImageBox(_selectedImage, 'Input image', _pickImage, true),
                _buildImageBox(_receivedImage, 'Mask image', null, false),
              ],
            ),
          ),
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.23,
            child: Row(
              children: [
                _buildImageBox(_outputImage, 'Output image', null, false),
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 32,
                    vertical: 24,
                  ),
                  child: _isLoading || _isGPTLoading
                      ? Column(
                          children: [
                            const CircularProgressIndicator(),
                            const SizedBox(height: 12),
                            Text(
                              _isGPTLoading
                                  ? 'Generating with GPT...'
                                  : 'Processing the image...',
                              style: TextStyle(color: Colors.grey.shade600),
                            ),
                          ],
                        )
                      : Column(
                          children: [
                            // Segment按钮
                            Align(
                              alignment: Alignment.centerRight,
                              child: ElevatedButton(
                                onPressed: _isLoading
                                    ? null
                                    : _sendImageToBackend,
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.blue.shade600,
                                  foregroundColor: Colors.white,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(20),
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 25,
                                    vertical: 15,
                                  ),
                                  elevation: 2,
                                  minimumSize: const Size(120, 50),
                                ),
                                child: const Text(
                                  'Segment',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w600,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                            const SizedBox(height: 16),
                            // Send to GPT按钮 - 根据条件改变颜色
                            Align(
                              alignment: Alignment.centerRight,
                              child: ElevatedButton(
                                onPressed: isGPTButtonEnabled
                                    ? _sendGPTData
                                    : null,
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: isGPTButtonEnabled
                                      ? Colors.green.shade600
                                      : Colors.grey.shade400,
                                  foregroundColor: Colors.white,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(20),
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 25,
                                    vertical: 15,
                                  ),
                                  elevation: 2,
                                  minimumSize: const Size(120, 50),
                                ),
                                child: const Text(
                                  'Send to GPT',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w600,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                          ],
                        ),
                ),
              ],
            ),
          ),
          const Expanded(child: SizedBox()),
          PromptTextField(
            controller: _adviceController,
            labelText: '输入您的背景需求',
            hintText: '我想要让GPT...',
            height: 70.0,
            autoFocus: true,
            maxLength: 500,
            textStyle: const TextStyle(fontSize: 16),
          ),
        ],
      ),
    );
  }
}
