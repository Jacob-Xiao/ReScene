import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import '../main.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';


class ProfilePage extends StatefulWidget {
  @override
  _ProfilePageState createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {

  @override
  void initState() {
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: null,
        title: Text('Settings'),
        automaticallyImplyLeading: false,
        backgroundColor: Colors.blue.shade700,
        foregroundColor: Colors.white,
      ),
      body: ListView(
        children: <Widget>[

        ],
      ),
    );
  }
}
