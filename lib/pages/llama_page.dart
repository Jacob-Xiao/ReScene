import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import '../models/llama_page/conversation_bar.dart';
import 'sub_pages/llama_page_subpages/llama_conversation_page.dart';
import '../test/Test_page1.dart';

class llama_page extends StatefulWidget {
  @override
  _llama_pageState createState() => _llama_pageState();
}

class _llama_pageState extends State<llama_page> {

  @override
  void initState() {
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: null,
        title: Text('Llama'),
        automaticallyImplyLeading: false,
        backgroundColor: Colors.blue.shade700,
        foregroundColor: Colors.white,
      ),
      body: ListView(
        children: <Widget>[
          llama_selecting_bar(
            iconName: 'Llama',
            title: 'Llama模型',
            content: 'Llama3.2-8B',
            onTap:(){
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => Llama_conversation_subpage()),
              );   
            },
            iconButtonName: '>',
          ),
          // llama_selecting_bar(
          //   iconName: '',
          //   title: 'Test',
          //   content: 'Do Test',
          //   onTap:(){
          //     Navigator.push(
          //       context,
          //       MaterialPageRoute(builder: (context) => IdeaPage_test()),
          //     );   
          //   },
          //   iconButtonName: '>',
          // ),
        ],
      ),
    );
  }
}
