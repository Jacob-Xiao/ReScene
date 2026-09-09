import 'package:flutter/material.dart';
import 'package:google_nav_bar/google_nav_bar.dart';

class MyBottomNavBar extends StatelessWidget {
  const MyBottomNavBar({super.key, required this.onTabChange});

  final void Function(int) onTabChange;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(25),
      decoration: BoxDecoration(
        color: Colors.white, // 设置导航条整体背景为白色
        borderRadius: BorderRadius.circular(25),
      ),
      child: GNav(
        onTabChange: onTabChange,
        color: Colors.blue.shade600,
        activeColor: Colors.white,
        tabBackgroundColor: Colors.blue.shade600,
        tabBorderRadius: 15,
        gap: 6,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        tabs: const [
          GButton(
            icon: Icons.light,
            text: 'Idea',
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          ),
          GButton(
            icon: Icons.computer,
            text: 'Llama',
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          ),
          GButton(
            icon: Icons.card_membership,
            text: 'Member',
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          ),
          GButton(
            icon: Icons.person,
            text: 'Profile',
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          ),
        ],
      ),
    );
  }
}
