import 'package:flutter/material.dart';

/// Multi-line prompt input with a live character counter.
class PromptTextField extends StatefulWidget {
  const PromptTextField({
    super.key,
    this.controller,
    required this.labelText,
    this.hintText = '',
    this.height = 60.0,
    this.border,
    this.autoFocus = false,
    this.onChanged,
    this.textStyle,
    this.maxLength,
  });

  final TextEditingController? controller;
  final String labelText;
  final String hintText;
  final double height;
  final InputBorder? border;
  final bool autoFocus;
  final ValueChanged<String>? onChanged;
  final TextStyle? textStyle;
  final int? maxLength;

  @override
  State<PromptTextField> createState() => _PromptTextFieldState();
}

class _PromptTextFieldState extends State<PromptTextField> {
  int _charCount = 0;

  @override
  void initState() {
    super.initState();
    _charCount = widget.controller?.text.length ?? 0;
    widget.controller?.addListener(_onControllerChanged);
  }

  @override
  void didUpdateWidget(PromptTextField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller?.removeListener(_onControllerChanged);
      widget.controller?.addListener(_onControllerChanged);
      _onControllerChanged();
    }
  }

  @override
  void dispose() {
    widget.controller?.removeListener(_onControllerChanged);
    super.dispose();
  }

  void _onControllerChanged() {
    final int newCount = widget.controller?.text.length ?? 0;
    if (newCount != _charCount) {
      setState(() => _charCount = newCount);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: widget.height,
      child: TextField(
        controller: widget.controller,
        maxLines: null,
        expands: true,
        maxLength: widget.maxLength,
        autofocus: widget.autoFocus,
        style: widget.textStyle,
        decoration: InputDecoration(
          labelText: widget.labelText,
          hintText: widget.hintText,
          border: widget.border ?? const OutlineInputBorder(),
          counterText: widget.maxLength != null
              ? '$_charCount/${widget.maxLength}'
              : null,
        ),
        onChanged: widget.onChanged,
      ),
    );
  }
}
