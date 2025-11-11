class SendData {
  static final SendData _instance = SendData._internal();
  factory SendData() => _instance;
  SendData._internal();

  String? _userId;
  String? _userPhone;

  void setUserId(String userId) {
    _userId = userId;
  }

  String? getUserId() {
    return _userId;
  }

  void setUserPhone(String userPhone) {
    _userPhone = userPhone;
  }

  String? getUserPhone() {
    return _userPhone;
  }
}