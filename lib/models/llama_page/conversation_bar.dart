import 'package:flutter/material.dart';


class llama_selecting_bar extends StatelessWidget {
  const llama_selecting_bar({
    Key? key,
    this.title,
    this.onTap,
    this.content="",
    this.textAlign= TextAlign.start,
    this.titleStyle,
    this.contentStyle,
    this.height,
    this.isShowArrow= true,
    this.imageName,
    this.iconName,
    this.iconButtonName,
    // required this.route,
  }): super(key: key);



  final GestureTapCallback? onTap;
  final String? title;
  final String? content;
  final TextAlign? textAlign;
  final TextStyle? titleStyle;
  final TextStyle? contentStyle;
  final double? height;
  final bool? isShowArrow;//是否显示右侧箭头
  final String? imageName;//左侧图片名字 不传则不显示图片
  final String? iconName;// Icons on the left. Won't get shown if not asked.
  final String? iconButtonName;
  // final String route;// Guiding route.

  @override
  Widget build(BuildContext context) {
    
    return GestureDetector(
      onTap: this.onTap,
      child: Container(
        height: this.height ?? 50.0,
        margin: EdgeInsets.only(left: 16, right: 16),
        width: double.infinity,
        decoration:  BoxDecoration(
          border: Border(
            //下面的分割线 width 这个参数应该是控制分割线高度的
            bottom: Divider.createBorderSide(context, color: Color(0xFFEEEEEE),width: 1)
          )
        ),
        child: 
          Row(
            children: <Widget>[
              this.imageName == null ? Container() :
              Image.asset(
                '${this.imageName}',
                width: 22,
                height: 22,
                ),
                this.iconName == null ? Container() :
                  Icon(
                    IconsMap[iconName], // 根据 iconName 获取图标
                    color: Color(0xFF333333),
                    size: 14.0,
                  ),
                Text(
                  this.title??'',
                  style: this.titleStyle ?? new TextStyle(
                    color: Color(0xFF333333),
                    fontSize: 14.0,
                  )
                ),
                Expanded(
                  child: Container(
                    padding: EdgeInsets.only(left: 16, right: 16),
                    child: Text(
                      this.content??'',
                      textAlign: this.textAlign,
                      overflow: TextOverflow.ellipsis,
                      style: this.contentStyle ?? new TextStyle(
                        fontSize: 14.0,
                        color: Color(0xFFCCCCCC),
                      )
                    ),
                  ),
                ),
                Icon(
                  IconsMap[iconButtonName], // 根据 iconName 获取图标
                  color: Color(0xFF333333),
                  size: 20.0,
                ),
                Text(
                  "   ", // 新文本内容
                  style: TextStyle(color: Color(0xFF333333), fontSize: 12.0), // 新文本样式
                ),
            ],
          ),
      ),
    );
  }
}

// 创建一个 Map 用于将 iconName 映射到 Icons 库中的图标
const Map<String, IconData> IconsMap = {
  'Llama' : Icons.computer_rounded,
  '>' : Icons.arrow_forward_ios,
  // 你可以在这里添加更多的图标映射
};

