import 'package:flutter/material.dart';

class PromptTextField extends StatelessWidget {
  final TextEditingController? controller;
  final String labelText;
  final String hintText;
  final double height;
  final InputBorder? border;
  final bool autoFocus;
  final ValueChanged<String>? onChanged;
  final TextStyle? textStyle;
  final int? maxLength;

  const PromptTextField({
    Key? key,
    this.controller,
    required this.labelText,
    this.hintText = '',
    this.height = 60.0,
    this.border,
    this.autoFocus = false,
    this.onChanged,
    this.textStyle,
    this.maxLength,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      child: TextField(
        controller: controller, // 直接使用外部controller
        maxLines: null,
        expands: true,
        maxLength: maxLength,
        autofocus: autoFocus,
        style: textStyle,
        decoration: InputDecoration(
          labelText: labelText,
          hintText: hintText,
          border: border ?? const OutlineInputBorder(),
          counterText: maxLength != null && controller != null
              ? '${controller!.text.length}/$maxLength'
              : null,
        ),
        onChanged: onChanged,
      ),
    );
  }
}