import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import 'package:google_nav_bar/google_nav_bar.dart';

class MyBottomNavBar extends StatelessWidget {
  void Function(int)? onTabChange;
  MyBottomNavBar({
    super.key,
    required this.onTabChange,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(25),
      decoration: BoxDecoration(
        color: Colors.white, // 设置导航条整体背景为白色
        borderRadius: BorderRadius.circular(25),
      ),
      child: GNav(
        onTabChange: (value) => onTabChange!(value),
        color: Colors.blue.shade600,
        activeColor: Colors.white,
        tabBackgroundColor: Colors.blue.shade600,
        tabBorderRadius: 15, // 可选：调整标签圆角
        gap: 6, // 可选：调整图标和文字间距
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10), // 减小垂直内边距
        tabs: const [
          GButton(
            icon: Icons.light,
            text: 'Idea',
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6), // 减小按钮内边距
          ),
          GButton(
            icon: Icons.computer,
            text: 'Llama',
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          ),
          GButton(
            icon: Icons.person,
            text: 'Profile',
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          ),
        ]
      )
    );
  }
}