import '../components/bottom_nav_bar.dart';
import '../const.dart';
import 'package:google_nav_bar/google_nav_bar.dart';
import 'package:flutter/material.dart';
import 'package:animate_do/animate_do.dart';
import 'llama_page.dart';
import 'profile_page.dart';
import 'idea_page.dart';

class HomePage extends StatefulWidget{
  const HomePage({Key? key}) : super(key: key);

  @override
  State<HomePage> createState() =>_HomePageState();
}

class _HomePageState extends State<HomePage> {

  int _selectedIndex=0;
  void navigateBottomBar(int index){
    setState(() {
      _selectedIndex=index;
    });
  }

  final List<Widget>_pages=[
    IdeaPage(),
    llama_page(),
    ProfilePage(),
  ];

  @override
  Widget build(BuildContext context){
    return Scaffold(
     backgroundColor: backgroundColor,
     bottomNavigationBar: MyBottomNavBar(
      onTabChange:(index) => navigateBottomBar(index),
    ),
    body:_pages[_selectedIndex], 
    );
  }
}

