import 'package:flutter/material.dart';

import '../components/bottom_nav_bar.dart';
import '../const.dart';
import 'idea_page.dart';
import 'llama_page.dart';
import 'profile_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _selectedIndex = 0;

  void _navigateBottomBar(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  // IndexedStack keeps every page's state alive while switching tabs,
  // so a picked image or an ongoing chat survives navigation.
  static const List<Widget> _pages = [IdeaPage(), LlamaPage(), ProfilePage()];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: backgroundColor,
      bottomNavigationBar: MyBottomNavBar(onTabChange: _navigateBottomBar),
      body: IndexedStack(index: _selectedIndex, children: _pages),
    );
  }
}
