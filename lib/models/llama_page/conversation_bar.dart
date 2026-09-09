import 'package:flutter/material.dart';

/// A settings-style row: optional icon, title, trailing content and arrow.
class LlamaSelectingBar extends StatelessWidget {
  const LlamaSelectingBar({
    super.key,
    this.title,
    this.onTap,
    this.content = '',
    this.textAlign = TextAlign.start,
    this.titleStyle,
    this.contentStyle,
    this.height,
    this.isShowArrow = true,
    this.imageName,
    this.iconName,
    this.iconButtonName,
  });

  final GestureTapCallback? onTap;
  final String? title;
  final String? content;
  final TextAlign? textAlign;
  final TextStyle? titleStyle;
  final TextStyle? contentStyle;
  final double? height;
  final bool? isShowArrow; //是否显示右侧箭头
  final String? imageName; //左侧图片名字 不传则不显示图片
  final String? iconName; // Icons on the left. Won't be shown if not asked.
  final String? iconButtonName;

  static const Map<String, IconData> _iconsMap = {
    'Llama': Icons.computer_rounded,
    '>': Icons.arrow_forward_ios,
    // 你可以在这里添加更多的图标映射
  };

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: height ?? 50.0,
        margin: const EdgeInsets.only(left: 16, right: 16),
        width: double.infinity,
        decoration: BoxDecoration(
          border: Border(
            //下面的分割线 width 这个参数应该是控制分割线高度的
            bottom: Divider.createBorderSide(
              context,
              color: const Color(0xFFEEEEEE),
              width: 1,
            ),
          ),
        ),
        child: Row(
          children: <Widget>[
            if (imageName != null)
              Image.asset(
                imageName!,
                width: 22,
                height: 22,
                errorBuilder: (_, __, ___) => const SizedBox.shrink(),
              ),
            if (iconName != null)
              Icon(
                _iconsMap[iconName!],
                color: const Color(0xFF333333),
                size: 14.0,
              ),
            Text(
              title ?? '',
              style:
                  titleStyle ??
                  const TextStyle(color: Color(0xFF333333), fontSize: 14.0),
            ),
            Expanded(
              child: Container(
                padding: const EdgeInsets.only(left: 16, right: 16),
                child: Text(
                  content ?? '',
                  textAlign: textAlign,
                  overflow: TextOverflow.ellipsis,
                  style:
                      contentStyle ??
                      const TextStyle(fontSize: 14.0, color: Color(0xFFCCCCCC)),
                ),
              ),
            ),
            if (isShowArrow ?? true)
              Icon(
                _iconsMap[iconButtonName ?? '>'],
                color: const Color(0xFF333333),
                size: 20.0,
              ),
            const Text(
              '   ',
              style: TextStyle(color: Color(0xFF333333), fontSize: 12.0),
            ),
          ],
        ),
      ),
    );
  }
}
