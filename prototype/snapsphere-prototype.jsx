import { useState, useEffect, useRef } from "react";
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StatusBar, SafeAreaView, Dimensions,
  Animated, KeyboardAvoidingView, Platform, Modal, Image,
  ActivityIndicator,
} from "react-native";

const USE_MOCK_FIREBASE = true;

const FIREBASE_CONFIG = {
  apiKey:            "AIzaSy_YOUR_KEY_HERE",
  authDomain:        "snapsphere-pk.firebaseapp.com",
  databaseURL:       "https://snapsphere-pk-default-rtdb.firebaseio.com",
  projectId:         "snapsphere-pk",
  storageBucket:     "snapsphere-pk.appspot.com",
  messagingSenderId: "123456789",
  appId:             "1:123456789:web:abcdef",
};

const _MOCK = {
  availability: {},
  bookings:     {},
  chats:        {},
  notifications:{},
};

setTimeout(() => {
  _pushNotif(1, { title:"Welcome to SnapSphere! 📷", body:"Book Pakistan's top photographers with AI recommendations.", type:"welcome" });
  _pushNotif(1, { title:"Booking Reminder 📅",         body:"Your shoot with Zara Malik is in 3 days!",                  type:"reminder" });
}, 600);

function _pushNotif(userId, notif) {
  if (!_MOCK.notifications[userId]) _MOCK.notifications[userId] = {};
  const id = "n_" + Date.now() + "_" + Math.random().toString(36).slice(2,5);
  _MOCK.notifications[userId][id] = { ...notif, id, read: false, timestamp: Date.now() };
}

const FB = {
  onAvailability(photogId, callback) {
    if (USE_MOCK_FIREBASE) {
      callback(_MOCK.availability[photogId] ?? true);
      const iv = setInterval(() => {
        callback(_MOCK.availability[photogId] ?? true);
      }, 20000);
      return () => clearInterval(iv);
    }
  },

  setAvailability(photogId, val) {
    if (USE_MOCK_FIREBASE) { _MOCK.availability[photogId] = val; return; }
  },

  onBookings(userId, callback) {
    if (USE_MOCK_FIREBASE) {
      const get = () => Object.values(_MOCK.bookings).filter(b => b.userId === userId);
      callback(get());
      const iv = setInterval(() => callback(get()), 5000);
      return () => clearInterval(iv);
    }
  },

  addBooking(data) {
    if (USE_MOCK_FIREBASE) {
      const id = "bk_" + Date.now();
      const booking = { ...data, id, status: "confirmed", createdAt: Date.now() };
      _MOCK.bookings[id] = booking;
      _MOCK.availability[data.photogId] = false;
      _pushNotif(data.userId, {
        title: "Booking Confirmed! 🎉",
        body:  `Your shoot with ${data.photog} on ${data.date} is locked in.`,
        type:  "booking_confirmed",
      });
      return { success: true, booking };
    }
  },

  getChatId: (uid, pid) => `chat_${Math.min(uid,pid)}_${Math.max(uid,pid)}`,

  onMessages(chatId, callback) {
    if (USE_MOCK_FIREBASE) {
      const get = () => Object.values(_MOCK.chats[chatId] || {}).sort((a,b)=>a.ts-b.ts);
      callback(get());
      const iv = setInterval(() => callback(get()), 1500);
      return () => clearInterval(iv);
    }
  },

  sendMsg(chatId, msg) {
    if (USE_MOCK_FIREBASE) {
      if (!_MOCK.chats[chatId]) _MOCK.chats[chatId] = {};
      const id = "m_" + Date.now();
      _MOCK.chats[chatId][id] = { ...msg, id, ts: Date.now() };
      return;
    }
  },

  onNotifications(userId, callback) {
    if (USE_MOCK_FIREBASE) {
      const get = () => Object.values(_MOCK.notifications[userId] || {}).sort((a,b)=>b.timestamp-a.timestamp);
      callback(get());
      const iv = setInterval(() => callback(get()), 2000);
      return () => clearInterval(iv);
    }
  },

  markRead(userId, notifId) {
    if (USE_MOCK_FIREBASE) {
      if (_MOCK.notifications[userId]?.[notifId]) _MOCK.notifications[userId][notifId].read = true;
      return;
    }
  },

  pushNotif: _pushNotif,
};

function NotificationBell({ userId, onPress }) {
  const [unread, setUnread] = useState(0);
  const pulse = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const unsub = FB.onNotifications(userId, notifs => {
      const count = notifs.filter(n => !n.read).length;
      setUnread(prev => {
        if (count > prev && prev > 0) {
          Animated.sequence([
            Animated.timing(pulse, { toValue:1.35, duration:180, useNativeDriver:true }),
            Animated.timing(pulse, { toValue:1,    duration:180, useNativeDriver:true }),
          ]).start();
        }
        return count;
      });
    });
    return unsub;
  }, [userId]);
  return (
    <TouchableOpacity onPress={onPress} style={{ position:"relative", padding:4 }}>
      <Animated.Text style={{ fontSize:22, transform:[{scale:pulse}] }}>🔔</Animated.Text>
      {unread > 0 && (
        <View style={{ position:"absolute", top:0, right:0, minWidth:17, height:17, borderRadius:9, backgroundColor:C.red, alignItems:"center", justifyContent:"center", borderWidth:2, borderColor:C.bg, paddingHorizontal:2 }}>
          <Text style={{ fontSize:9, fontWeight:"800", color:"#fff" }}>{unread > 9 ? "9+" : unread}</Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

function NotificationsPanel({ userId, visible, onClose }) {
  const [notifs, setNotifs] = useState([]);
  useEffect(() => {
    if (!visible) return;
    const unsub = FB.onNotifications(userId, setNotifs);
    return unsub;
  }, [userId, visible]);
  const ICONS = { booking_confirmed:"✅", new_booking:"📅", reminder:"⏰", welcome:"👋", message:"💬" };
  if (!visible) return null;
  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <View style={{ flex:1, backgroundColor:"#000000BB" }}>
        <TouchableOpacity style={{ flex:1 }} activeOpacity={1} onPress={onClose}/>
        <View style={{ backgroundColor:C.surface, borderTopLeftRadius:24, borderTopRightRadius:24, borderWidth:1, borderColor:C.border, maxHeight: height * 0.75, minHeight:300 }}>
          <View style={{ padding:20, flexDirection:"row", justifyContent:"space-between", alignItems:"center", borderBottomWidth:1, borderBottomColor:C.border }}>
            <View>
              <Text style={{ fontSize:18, fontWeight:"800", color:C.text }}>Notifications</Text>
              <View style={{ flexDirection:"row", alignItems:"center", gap:5, marginTop:3 }}>
                <View style={{ width:6, height:6, borderRadius:3, backgroundColor:C.green }}/>
                <Text style={{ fontSize:10, color:C.green }}>Live via Firebase</Text>
              </View>
            </View>
            <TouchableOpacity onPress={onClose} style={{ width:34, height:34, borderRadius:17, backgroundColor:C.card, alignItems:"center", justifyContent:"center", borderWidth:1, borderColor:C.border }}>
              <Text style={{ color:C.text, fontSize:16 }}>✕</Text>
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={{ padding:16, gap:10 }}>
            {notifs.length === 0 ? (
              <View style={{ alignItems:"center", paddingVertical:40 }}>
                <Text style={{ fontSize:32, marginBottom:12 }}>🔔</Text>
                <Text style={{ fontSize:14, color:C.sub }}>No notifications yet</Text>
              </View>
            ) : notifs.map(n => (
              <TouchableOpacity key={n.id} onPress={() => FB.markRead(userId, n.id)}
                style={{ backgroundColor:n.read?C.card:C.gold+"11", borderWidth:1, borderColor:n.read?C.border:C.gold+"44", borderRadius:14, padding:14, flexDirection:"row", gap:12, alignItems:"flex-start" }}>
                <View style={{ width:40, height:40, borderRadius:20, backgroundColor:C.gold+"22", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                  <Text style={{ fontSize:18 }}>{ICONS[n.type] || "🔔"}</Text>
                </View>
                <View style={{ flex:1 }}>
                  <Text style={{ fontSize:13, fontWeight:"700", color:C.text, marginBottom:3 }}>{n.title}</Text>
                  <Text style={{ fontSize:11, color:C.sub, lineHeight:17 }}>{n.body}</Text>
                  <Text style={{ fontSize:10, color:C.dim, marginTop:5 }}>
                    {n.timestamp ? new Date(n.timestamp).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}) : "Just now"}
                  </Text>
                </View>
                {!n.read && <View style={{ width:8, height:8, borderRadius:4, backgroundColor:C.gold, marginTop:4 }}/>}
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function ChatScreen({ currentUser, photographer, onBack }) {
  const chatId = FB.getChatId(currentUser.id, photographer.id);
  const [messages, setMessages] = useState([]);
  const [input,    setInput]    = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!_MOCK.chats[chatId] || Object.keys(_MOCK.chats[chatId]).length === 0) {
      setTimeout(() => FB.sendMsg(chatId, {
        senderId: photographer.id,
        senderName: photographer.name,
        text: `Hi! I'm ${photographer.name}. How can I help you? 😊`,
      }), 600);
    }
    const unsub = FB.onMessages(chatId, msgs => {
      setMessages(msgs);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated:true }), 100);
    });
    return unsub;
  }, [chatId]);

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    FB.sendMsg(chatId, { senderId:currentUser.id, senderName:currentUser.name, text });
    setTimeout(() => {
      const replies = [
        "Sure! I'd love to work with you on that 📸",
        `My rate is PKR ${Math.round(photographer.price/8).toLocaleString()}/hr. Shall we confirm?`,
        "That date works for me! Let's lock it in.",
        "Great! Can you share more details about the shoot?",
        "Absolutely! I specialize in exactly that style.",
      ];
      FB.sendMsg(chatId, {
        senderId: photographer.id,
        senderName: photographer.name,
        text: replies[Math.floor(Math.random() * replies.length)],
      });
    }, 1800 + Math.random() * 1500);
  };

  const isMe = msg => msg.senderId === currentUser.id;

  return (
    <View style={{ flex:1, backgroundColor:C.bg }}>
      <View style={{ backgroundColor:C.card, padding:16, paddingTop:20, flexDirection:"row", alignItems:"center", gap:12, borderBottomWidth:1, borderBottomColor:C.border }}>
        <TouchableOpacity onPress={onBack} style={{ backgroundColor:C.surface, borderWidth:1, borderColor:C.border, borderRadius:10, paddingHorizontal:12, paddingVertical:6 }}>
          <Text style={{ color:C.text, fontSize:12 }}>← Back</Text>
        </TouchableOpacity>
        <View style={{ width:38, height:38, borderRadius:19, backgroundColor:photographer.color+"99", alignItems:"center", justifyContent:"center", borderWidth:1.5, borderColor:photographer.color+"88" }}>
          <Text style={{ fontSize:13, fontWeight:"700", color:"#fff" }}>{photographer.img}</Text>
        </View>
        <View style={{ flex:1 }}>
          <Text style={{ fontSize:14, fontWeight:"700", color:C.text }}>{photographer.name}</Text>
          <View style={{ flexDirection:"row", alignItems:"center", gap:5, marginTop:2 }}>
            <View style={{ width:6, height:6, borderRadius:3, backgroundColor:C.green }}/>
            <Text style={{ fontSize:10, color:C.green }}>Online · Firebase Live</Text>
          </View>
        </View>
        <View style={{ backgroundColor:C.greenDim, borderWidth:1, borderColor:C.green+"44", borderRadius:8, paddingHorizontal:8, paddingVertical:4 }}>
          <Text style={{ fontSize:9, fontWeight:"800", color:C.green }}>🔥 LIVE</Text>
        </View>
      </View>
      <ScrollView ref={scrollRef} style={{ flex:1, padding:16 }} contentContainerStyle={{ gap:10, paddingBottom:16 }}>
        <View style={{ alignSelf:"center", backgroundColor:C.card, borderWidth:1, borderColor:C.border, borderRadius:20, paddingHorizontal:14, paddingVertical:6, flexDirection:"row", alignItems:"center", gap:6 }}>
          <View style={{ width:5, height:5, borderRadius:3, backgroundColor:C.green }}/>
          <Text style={{ fontSize:10, color:C.sub }}>Messages sync in real-time via Firebase</Text>
        </View>
        {messages.map(msg => (
          <View key={msg.id} style={{ alignItems: isMe(msg) ? "flex-end" : "flex-start" }}>
            {!isMe(msg) && <Text style={{ fontSize:10, color:C.sub, marginBottom:3, marginLeft:4 }}>{msg.senderName}</Text>}
            <View style={{ maxWidth:"78%", backgroundColor: isMe(msg)?C.gold:C.card, borderRadius:18, borderBottomRightRadius:isMe(msg)?4:18, borderBottomLeftRadius:isMe(msg)?18:4, padding:12, borderWidth:1, borderColor:isMe(msg)?C.gold+"88":C.border }}>
              <Text style={{ fontSize:13, color:isMe(msg)?C.bg:C.text, lineHeight:20 }}>{msg.text}</Text>
              <Text style={{ fontSize:9, color:isMe(msg)?C.bg+"99":C.dim, marginTop:4, alignSelf:"flex-end" }}>
                {msg.ts ? new Date(msg.ts).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}) : ""}
              </Text>
            </View>
          </View>
        ))}
      </ScrollView>
      <KeyboardAvoidingView behavior={Platform.OS==="ios"?"padding":undefined}>
        <View style={{ backgroundColor:C.card, padding:12, paddingBottom:Platform.OS==="ios"?28:12, flexDirection:"row", alignItems:"flex-end", gap:10, borderTopWidth:1, borderTopColor:C.border }}>
          <TextInput value={input} onChangeText={setInput} placeholder="Type a message..." placeholderTextColor={C.dim} multiline
            style={{ flex:1, color:C.text, fontSize:13, backgroundColor:C.surface, borderRadius:20, paddingHorizontal:16, paddingVertical:10, borderWidth:1, borderColor:C.borderMid, maxHeight:100 }}/>
          <TouchableOpacity onPress={send} disabled={!input.trim()}
            style={{ width:44, height:44, borderRadius:22, backgroundColor:input.trim()?C.gold:C.card, borderWidth:1, borderColor:input.trim()?C.gold:C.border, alignItems:"center", justifyContent:"center" }}>
            <Text style={{ fontSize:18, color:input.trim()?C.bg:C.dim }}>↑</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const { width, height } = Dimensions.get("window");

const DJANGO_BASE_URL = null;

const API = {
  async getRecommendations(userId, topN = 10) {
    if (!DJANGO_BASE_URL) return { success: false, reason: "no_server" };
    try {
      const res = await fetch(
        `${DJANGO_BASE_URL}/api/recommend/${userId}/?top_n=${topN}`,
        { headers: { "Content-Type": "application/json" } }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return { success: true, data };
    } catch (e) {
      console.warn("API Error (using local fallback):", e.message);
      return { success: false, reason: "network_error" };
    }
  },

  async getPhotographers() {
    if (!DJANGO_BASE_URL) return { success: false };
    try {
      const res = await fetch(`${DJANGO_BASE_URL}/api/photographers/`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return { success: true, data };
    } catch (e) {
      return { success: false };
    }
  },

  async createBooking(bookingData, token) {
    if (!DJANGO_BASE_URL) return { success: false };
    try {
      const res = await fetch(`${DJANGO_BASE_URL}/api/bookings/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(bookingData),
      });
      const data = await res.json();
      return res.ok ? { success: true, data } : { success: false, error: data };
    } catch (e) {
      return { success: false, error: e.message };
    }
  },

  async login(email, password) {
    if (!DJANGO_BASE_URL) return { success: false };
    try {
      const res = await fetch(`${DJANGO_BASE_URL}/api/auth/login/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      return res.ok ? { success: true, data } : { success: false, error: data };
    } catch (e) {
      return { success: false };
    }
  },
};

const C = {
  bg:        "#080A0E",
  surface:   "#0F1116",
  card:      "#161A22",
  cardHover: "#1C2130",
  border:    "#232836",
  borderMid: "#2E3548",
  gold:      "#D4A843",
  goldLight: "#EFC96A",
  goldDim:   "#7A6128",
  text:      "#EEE9E0",
  sub:       "#9A95A0",
  dim:       "#4E4A55",
  blue:      "#4A8FD4",
  blueDim:   "#1E3A58",
  green:     "#3DB87A",
  greenDim:  "#1A3D2E",
  red:       "#E05A5A",
  redDim:    "#3D1A1A",
  amber:     "#E0973A",
  amberDim:  "#3D2A10",
};

const USER_STORE = {
  users: [
    { id: "user_001", name: "Demo User",  email: "demo@snapsphere.pk",  password: "demo123",  phone: "03001234567", city: "Islamabad", role: "buyer"        },
    { id: "user_002", name: "Admin User", email: "admin@snapsphere.pk", password: "admin123", phone: "03009876543", city: "Lahore",    role: "admin"        },
    { id: "user_003", name: "Zara Malik", email: "zara@snapsphere.pk",  password: "zara123",  phone: "03111234567", city: "Islamabad", role: "photographer" },
  ],
  nextId: 4,
  register(userData) {
    const exists = this.users.find(u => u.email.toLowerCase() === userData.email.toLowerCase());
    if (exists) return { success: false, error: "An account with this email already exists." };
    const newUser = { ...userData, id: `user_${String(this.nextId).padStart(3,"0")}` };
    this.nextId++;
    this.users.push(newUser);
    return { success: true, user: newUser };
  },
  login(email, password) {
    const user = this.users.find(u =>
      u.email.toLowerCase() === email.toLowerCase() && u.password === password
    );
    if (!user) return { success: false, error: "Invalid email or password." };
    return { success: true, user, token: "mock-jwt-token-" + user.id };
  },
};

const BOOKINGS_STORE = {
  bookings: [
    { id:1, userId:"user_001", photogId:3, photog:"Sana Tariq",  date:"2025-04-30", type:"Travel Blog",   status:"completed", amount:6000,  color:"#2A8B5E", hours:6 },
    { id:2, userId:"user_001", photogId:1, photog:"Zara Malik",  date:"2025-05-15", type:"Wedding Shoot", status:"confirmed", amount:8500,  color:"#8B4E2A", hours:8 },
    { id:3, userId:"user_001", photogId:2, photog:"Bilal Raza",  date:"2025-05-20", type:"Fashion Shoot", status:"confirmed", amount:12000, color:"#2A5E8B", hours:8 },
  ],
  nextId: 4,
  isPhotographerBooked(photogId, date) {
    return this.bookings.some(b =>
      b.photogId === photogId && b.date === date &&
      b.status !== "completed" && b.status !== "cancelled"
    );
  },
  addBooking(booking) {
    if (this.isPhotographerBooked(booking.photogId, booking.date)) {
      return { success: false, error: "This photographer is already booked on that date." };
    }
    const newBooking = { ...booking, id: this.nextId++ };
    this.bookings.push(newBooking);
    return { success: true, booking: newBooking };
  },
  getUserBookings(userId) { return this.bookings.filter(b => b.userId === userId); },
  getPhotographerBookings(photogId) { return this.bookings.filter(b => b.photogId === photogId); },
  getBookedDates(photogId) {
    return this.bookings
      .filter(b => b.photogId === photogId && b.status !== "completed" && b.status !== "cancelled")
      .map(b => b.date);
  },
};

const PHOTOGRAPHERS = [
  { id:1, apiId:"9yKzy9PApeiPPOUJEtnvkg", name:"Zara Malik",   role:"Wedding & Portrait",         rating:4.9, reviews:214, price:8500,  city:"Islamabad",  tags:["Wedding","Portrait"],      color:"#8B4E2A", avail:true,  bookings:48, img:"ZM", bio:"Award-winning wedding photographer with 7+ years capturing timeless moments across Pakistan." },
  { id:2, apiId:"UsFtqoBl7naz8AVUBZMjQQ", name:"Bilal Raza",   role:"Commercial & Fashion",       rating:4.8, reviews:178, price:12000, city:"Lahore",     tags:["Fashion","Commercial"],    color:"#2A5E8B", avail:true,  bookings:62, img:"BR", bio:"Fashion and commercial photographer published in Vogue Pakistan and Dawn Images." },
  { id:3, apiId:"4bEjOAf7mnxUFKbFTcQD3Q", name:"Sana Tariq",   role:"Nature & Travel",            rating:4.7, reviews:95,  price:6000,  city:"Rawalpindi", tags:["Nature","Travel"],         color:"#2A8B5E", avail:false, bookings:31, img:"ST", bio:"Travel photographer exploring the landscapes of KPK, Gilgit-Baltistan and beyond." },
  { id:4, apiId:"RESDUcs7fIiihp38-d6_6g", name:"Omar Sheikh",  role:"Event & Corporate",          rating:4.6, reviews:142, price:9500,  city:"Karachi",    tags:["Event","Corporate"],       color:"#5E2A8B", avail:true,  bookings:55, img:"OS", bio:"Corporate event photographer trusted by top Fortune 500 companies in Pakistan." },
  { id:5, apiId:"K7lWdNUhCbcnEvI0NhGewQ", name:"Ayesha Noor",  role:"Newborn & Family",           rating:5.0, reviews:67,  price:7000,  city:"Islamabad",  tags:["Family","Newborn"],        color:"#8B2A5E", avail:true,  bookings:29, img:"AN", bio:"Specialist in newborn and family lifestyle photography." },
  { id:6, apiId:"cE27W9R7gymm0mBCo3iodA", name:"Kamran Javed", role:"Architecture & Real Estate", rating:4.5, reviews:88,  price:11000, city:"Lahore",     tags:["Architecture","Interior"], color:"#5E7A2A", avail:true,  bookings:40, img:"KJ", bio:"Architectural photographer with a precise eye for geometry, light and space." },
];

const PORTFOLIO_PHOTOS = {
  1: [
    { id:1, uri:"https://images.unsplash.com/photo-1519741497674-611481863552?w=800&q=80", label:"Wedding Ceremony", featured:true },
    { id:2, uri:"https://images.unsplash.com/photo-1606800052052-a08af7148866?w=600&q=80", label:"Bride Portrait" },
    { id:3, uri:"https://images.unsplash.com/photo-1583939003579-730e3918a45a?w=600&q=80", label:"Reception" },
    { id:4, uri:"https://images.unsplash.com/photo-1591604466107-ec97de577aff?w=600&q=80", label:"Couple Shoot" },
    { id:5, uri:"https://images.unsplash.com/photo-1469371670807-013ccf25f16a?w=600&q=80", label:"Outdoor Portrait" },
    { id:6, uri:"https://images.unsplash.com/photo-1511285560929-80b456fea0bc?w=600&q=80", label:"Candid Moment" },
  ],
  2: [
    { id:1, uri:"https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80", label:"Fashion Editorial", featured:true },
    { id:2, uri:"https://images.unsplash.com/photo-1509631179647-0177331693ae?w=600&q=80", label:"Studio Fashion" },
    { id:3, uri:"https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=600&q=80", label:"Commercial Ad" },
    { id:4, uri:"https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600&q=80", label:"Runway Look" },
    { id:5, uri:"https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=600&q=80", label:"Magazine Cover" },
    { id:6, uri:"https://images.unsplash.com/photo-1483985988355-763728e1935b?w=600&q=80", label:"Brand Campaign" },
  ],
  3: [
    { id:1, uri:"https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&q=80", label:"Mountain Peaks", featured:true },
    { id:2, uri:"https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=600&q=80", label:"Golden Hour" },
    { id:3, uri:"https://images.unsplash.com/photo-1501854140801-50d01698950b?w=600&q=80", label:"Valley View" },
    { id:4, uri:"https://images.unsplash.com/photo-1470770903676-69b98201ea1c?w=600&q=80", label:"Sunrise Lake" },
    { id:5, uri:"https://images.unsplash.com/photo-1519904981063-b0cf448d479e?w=600&q=80", label:"Travel Story" },
    { id:6, uri:"https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=600&q=80", label:"Coastal Scene" },
  ],
  4: [
    { id:1, uri:"https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800&q=80", label:"Corporate Event", featured:true },
    { id:2, uri:"https://images.unsplash.com/photo-1587825140708-dfaf72ae4b04?w=600&q=80", label:"Conference" },
    { id:3, uri:"https://images.unsplash.com/photo-1511578314322-379afb476865?w=600&q=80", label:"Gala Dinner" },
    { id:4, uri:"https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=600&q=80", label:"Panel Discussion" },
    { id:5, uri:"https://images.unsplash.com/photo-1475721027785-f74eccf877e2?w=600&q=80", label:"Stage Keynote" },
    { id:6, uri:"https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=600&q=80", label:"Team Photo" },
  ],
  5: [
    { id:1, uri:"https://images.unsplash.com/photo-1555252333-9f8e92e65df9?w=800&q=80", label:"Newborn Bliss", featured:true },
    { id:2, uri:"https://images.unsplash.com/photo-1476703993599-0035a21b17a9?w=600&q=80", label:"Family Moment" },
    { id:3, uri:"https://images.unsplash.com/photo-1491013516836-7db643ee125a?w=600&q=80", label:"Baby Portrait" },
    { id:4, uri:"https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?w=600&q=80", label:"Family Outdoor" },
    { id:5, uri:"https://images.unsplash.com/photo-1548199973-03cce0bbc87b?w=600&q=80", label:"Park Session" },
    { id:6, uri:"https://images.unsplash.com/photo-1560969184-10fe8719e047?w=600&q=80", label:"Sibling Love" },
  ],
  6: [
    { id:1, uri:"https://images.unsplash.com/photo-1487958449943-2429e8be8625?w=800&q=80", label:"Modern Architecture", featured:true },
    { id:2, uri:"https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=600&q=80", label:"Luxury Interior" },
    { id:3, uri:"https://images.unsplash.com/photo-1503174971373-b1f69850bded?w=600&q=80", label:"Geometric Lines" },
    { id:4, uri:"https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=600&q=80", label:"Real Estate" },
    { id:5, uri:"https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=600&q=80", label:"Skyline View" },
    { id:6, uri:"https://images.unsplash.com/photo-1507089947368-19c1da9775ae?w=600&q=80", label:"Glass Facade" },
  ],
};

const ANALYTICS = {
  totalBookings:186, totalRevenue:248500, avgRating:4.78, profileViews:3241,
  monthlyData:[
    {month:"Jan",bookings:12,revenue:98000},{month:"Feb",bookings:18,revenue:142000},
    {month:"Mar",bookings:15,revenue:118000},{month:"Apr",bookings:22,revenue:187000},
    {month:"May",bookings:28,revenue:235000},{month:"Jun",bookings:19,revenue:162000},
  ],
};

function getLocalRecommendations(userId, userBookings) {
  const bookedIds = userBookings.map(b => b.photogId);

  if (bookedIds.length > 0) {
    const bookedPhotogs = PHOTOGRAPHERS.filter(p => bookedIds.includes(p.id));
    const preferredTags = [...new Set(bookedPhotogs.flatMap(p => p.tags))];

    const scored = PHOTOGRAPHERS
      .filter(p => !bookedIds.includes(p.id))
      .map(p => {
        const tagMatch = p.tags.filter(t => preferredTags.includes(t)).length;
        const score = tagMatch * 0.8 + p.rating * 0.5 + (p.avail ? 0.3 : 0);
        return { ...p, predictedRating: Math.min(5, score).toFixed(2), isPersonalized: true };
      })
      .sort((a, b) => b.predictedRating - a.predictedRating);

    return { type: "personalized", photographers: scored };
  }

  const topRated = [...PHOTOGRAPHERS]
    .sort((a, b) => {
      const scoreA = (a.reviews / (a.reviews + 10)) * a.rating + (10 / (a.reviews + 10)) * 4.0;
      const scoreB = (b.reviews / (b.reviews + 10)) * b.rating + (10 / (b.reviews + 10)) * 4.0;
      return scoreB - scoreA;
    })
    .map(p => ({ ...p, predictedRating: p.rating.toFixed(2), isPersonalized: false }));

  return { type: "popular", photographers: topRated };
}

const Avatar = ({ initials, color, size = 44 }) => (
  <View style={{ width:size, height:size, borderRadius:size/2, backgroundColor:color+"99", alignItems:"center", justifyContent:"center", borderWidth:1.5, borderColor:color+"88", flexShrink:0 }}>
    <Text style={{ fontSize:size*0.3, fontWeight:"700", color:"#fff", letterSpacing:1 }}>{initials}</Text>
  </View>
);

const Stars = ({ rating }) => (
  <Text style={{ fontSize:11, letterSpacing:1 }}>
    {[1,2,3,4,5].map(i => (
      <Text key={i} style={{ color: i<=Math.round(rating) ? C.gold : C.dim }}>★</Text>
    ))}
  </Text>
);

const Badge = ({ label, color=C.gold }) => (
  <View style={{ paddingHorizontal:9, paddingVertical:3, borderRadius:20, borderWidth:1, borderColor:color+"55", backgroundColor:color+"18", marginRight:4 }}>
    <Text style={{ fontSize:10, fontWeight:"600", color, letterSpacing:0.7, textTransform:"uppercase" }}>{label}</Text>
  </View>
);

const StatusBadge = ({ status }) => {
  const map = {
    confirmed:{ color:C.green, bg:C.greenDim, label:"Confirmed" },
    pending:  { color:C.amber, bg:C.amberDim, label:"Pending"   },
    completed:{ color:C.blue,  bg:C.blueDim,  label:"Completed" },
    cancelled:{ color:C.red,   bg:C.redDim,   label:"Cancelled" },
  };
  const s = map[status] || map.pending;
  return (
    <View style={{ paddingHorizontal:10, paddingVertical:4, borderRadius:6, backgroundColor:s.bg, borderWidth:1, borderColor:s.color+"44" }}>
      <Text style={{ fontSize:10, fontWeight:"700", color:s.color, letterSpacing:0.6, textTransform:"uppercase" }}>{s.label}</Text>
    </View>
  );
};

const SectionHeader = ({ title, action, onAction }) => (
  <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"center", paddingHorizontal:20, marginBottom:14 }}>
    <Text style={{ fontSize:16, fontWeight:"700", color:C.text }}>{title}</Text>
    {action && (
      <TouchableOpacity onPress={onAction}>
        <Text style={{ fontSize:11, color:C.gold, letterSpacing:0.5 }}>{action} →</Text>
      </TouchableOpacity>
    )}
  </View>
);

function Toast({ message, type="error", onDone }) {
  const opacity = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.sequence([
      Animated.timing(opacity,{ toValue:1, duration:250, useNativeDriver:true }),
      Animated.delay(2600),
      Animated.timing(opacity,{ toValue:0, duration:300, useNativeDriver:true }),
    ]).start(() => onDone && onDone());
  }, []);
  const bg     = type==="success" ? C.greenDim : type==="warn" ? C.amberDim : C.redDim;
  const border = type==="success" ? C.green    : type==="warn" ? C.amber    : C.red;
  const icon   = type==="success" ? "✓"        : type==="warn" ? "⚠"       : "✕";
  return (
    <Animated.View style={{ position:"absolute", top:16, left:16, right:16, zIndex:999, opacity, flexDirection:"row", alignItems:"center", gap:10, backgroundColor:bg, borderWidth:1, borderColor:border+"55", borderRadius:12, padding:14 }}>
      <Text style={{ fontSize:14, color:border }}>{icon}</Text>
      <Text style={{ flex:1, fontSize:12, color:C.text, lineHeight:18 }}>{message}</Text>
    </Animated.View>
  );
}

const AIBadge = ({ score, isPersonalized }) => (
  <View style={{ flexDirection:"row", alignItems:"center", gap:4, backgroundColor: isPersonalized ? C.gold+"18" : C.blue+"18", paddingHorizontal:8, paddingVertical:3, borderRadius:8, borderWidth:1, borderColor: isPersonalized ? C.gold+"44" : C.blue+"44" }}>
    <Text style={{ fontSize:9 }}>🤖</Text>
    <Text style={{ fontSize:9, fontWeight:"700", color: isPersonalized ? C.gold : C.blue, letterSpacing:0.5 }}>
      {isPersonalized ? `AI MATCH · ${score}★` : `TOP RATED · ${score}★`}
    </Text>
  </View>
);

function RoleSwitcher({ currentUser, onSwitch }) {
  const slideAnim = useRef(new Animated.Value(currentUser?.activeRole === "photographer" ? 1 : 0)).current;
  const isPhotog = currentUser?.activeRole === "photographer";

  const handleSwitch = () => {
    const toPhotog = !isPhotog;
    Animated.spring(slideAnim, { toValue: toPhotog ? 1 : 0, useNativeDriver: false, tension: 80, friction: 8 }).start();
    onSwitch(toPhotog ? "photographer" : "buyer");
  };

  const thumbLeft = slideAnim.interpolate({ inputRange:[0,1], outputRange:[3, 78] });
  const bgColor   = slideAnim.interpolate({ inputRange:[0,1], outputRange:[C.blueDim, C.goldDim] });

  return (
    <TouchableOpacity onPress={handleSwitch} activeOpacity={0.9}>
      <Animated.View style={{ width:156, height:38, borderRadius:20, backgroundColor:bgColor, borderWidth:1, borderColor:isPhotog ? C.gold+"55" : C.blue+"55", flexDirection:"row", alignItems:"center", paddingHorizontal:6, position:"relative" }}>
        <View style={{ position:"absolute", left:14, top:0, bottom:0, justifyContent:"center" }}>
          <Text style={{ fontSize:10, fontWeight:"700", color:!isPhotog ? C.blue : C.dim, letterSpacing:0.6 }}>🔍 BUYER</Text>
        </View>
        <View style={{ position:"absolute", right:10, top:0, bottom:0, justifyContent:"center" }}>
          <Text style={{ fontSize:10, fontWeight:"700", color:isPhotog ? C.gold : C.dim, letterSpacing:0.6 }}>📸 PRO</Text>
        </View>
        <Animated.View style={{ position:"absolute", left:thumbLeft, width:72, height:32, borderRadius:17, backgroundColor: isPhotog ? C.gold : C.blue, alignItems:"center", justifyContent:"center", shadowColor: isPhotog ? C.gold : C.blue, shadowOpacity:0.5, shadowRadius:8, elevation:4 }}>
          <Text style={{ fontSize:9, fontWeight:"800", color:C.bg, letterSpacing:0.5 }}>{isPhotog ? "PHOTOG" : "CLIENT"}</Text>
        </Animated.View>
      </Animated.View>
    </TouchableOpacity>
  );
}

function CalendarPicker({ selectedDate, onSelectDate, bookedDates = [], visible, onClose }) {
  const today = new Date();
  today.setHours(0,0,0,0);
  const [viewYear,  setViewYear]  = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const DAYS   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  const getDaysInMonth = (y, m) => new Date(y, m+1, 0).getDate();
  const getFirstDay    = (y, m) => new Date(y, m, 1).getDay();
  const prevMonth = () => { if (viewMonth===0){setViewMonth(11);setViewYear(v=>v-1);}else setViewMonth(v=>v-1); };
  const nextMonth = () => { if (viewMonth===11){setViewMonth(0);setViewYear(v=>v+1);}else setViewMonth(v=>v+1); };
  const dateStr = (y,m,d) => `${y}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
  const renderDays = () => {
    const days=getDaysInMonth(viewYear,viewMonth),first=getFirstDay(viewYear,viewMonth),cells=[];
    for(let i=0;i<first;i++) cells.push(<View key={`e${i}`} style={{width:"14.28%",padding:2}}/>);
    for(let d=1;d<=days;d++){
      const ds=dateStr(viewYear,viewMonth,d),dayDate=new Date(viewYear,viewMonth,d),isPast=dayDate<today,isBooked=bookedDates.includes(ds),isSel=ds===selectedDate,isToday=ds===dateStr(today.getFullYear(),today.getMonth(),today.getDate());
      let bg="transparent",border="transparent",txtCol=isPast?C.dim:C.text;
      if(isSel){bg=C.gold;border=C.gold;txtCol=C.bg;}
      else if(isBooked){bg=C.redDim;border=C.red+"44";txtCol=C.red;}
      else if(isToday){border=C.gold+"55";}
      cells.push(
        <TouchableOpacity key={d} disabled={isPast||isBooked} onPress={()=>{onSelectDate(ds);onClose();}} style={{width:"14.28%",padding:2}}>
          <View style={{aspectRatio:1,borderRadius:10,backgroundColor:bg,borderWidth:1,borderColor:border,alignItems:"center",justifyContent:"center"}}>
            <Text style={{fontSize:12,fontWeight:isSel?"800":"500",color:txtCol}}>{d}</Text>
            {isBooked&&!isSel&&<View style={{position:"absolute",bottom:2,width:4,height:4,borderRadius:2,backgroundColor:C.red}}/>}
          </View>
        </TouchableOpacity>
      );
    }
    return cells;
  };
  if(!visible) return null;
  return(
    <Modal transparent animationType="fade" visible={visible} onRequestClose={onClose}>
      <TouchableOpacity style={{flex:1,backgroundColor:"#000000CC"}} activeOpacity={1} onPress={onClose}>
        <View style={{flex:1,justifyContent:"center",alignItems:"center",padding:20}}>
          <TouchableOpacity activeOpacity={1}>
            <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.gold+"44",borderRadius:22,padding:20,width:Math.min(340,width-40)}}>
              <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",marginBottom:18}}>
                <TouchableOpacity onPress={prevMonth} style={{width:36,height:36,borderRadius:12,backgroundColor:C.surface,borderWidth:1,borderColor:C.border,alignItems:"center",justifyContent:"center"}}><Text style={{color:C.text,fontSize:16}}>‹</Text></TouchableOpacity>
                <Text style={{fontSize:15,fontWeight:"700",color:C.text}}>{MONTHS[viewMonth]} {viewYear}</Text>
                <TouchableOpacity onPress={nextMonth} style={{width:36,height:36,borderRadius:12,backgroundColor:C.surface,borderWidth:1,borderColor:C.border,alignItems:"center",justifyContent:"center"}}><Text style={{color:C.text,fontSize:16}}>›</Text></TouchableOpacity>
              </View>
              <View style={{flexDirection:"row",marginBottom:6}}>
                {DAYS.map(d=><View key={d} style={{width:"14.28%",alignItems:"center"}}><Text style={{fontSize:10,color:C.dim,fontWeight:"700",letterSpacing:0.5}}>{d}</Text></View>)}
              </View>
              <View style={{flexDirection:"row",flexWrap:"wrap"}}>{renderDays()}</View>
              <View style={{flexDirection:"row",gap:16,marginTop:16,paddingTop:14,borderTopWidth:1,borderTopColor:C.border,justifyContent:"center"}}>
                {[{col:C.gold,bg:C.gold,label:"Selected"},{col:C.red+"44",bg:C.redDim,label:"Booked"},{col:C.gold+"55",bg:"transparent",label:"Today"}].map(l=>(
                  <View key={l.label} style={{flexDirection:"row",alignItems:"center",gap:6}}>
                    <View style={{width:10,height:10,borderRadius:3,backgroundColor:l.bg,borderWidth:1,borderColor:l.col}}/>
                    <Text style={{fontSize:10,color:C.sub}}>{l.label}</Text>
                  </View>
                ))}
              </View>
            </View>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

function BookingConfirmedAnimation({ booking, onDone }) {
  const scale=useRef(new Animated.Value(0)).current,opacity=useRef(new Animated.Value(0)).current,checkSc=useRef(new Animated.Value(0)).current,ring1=useRef(new Animated.Value(0)).current,ring2=useRef(new Animated.Value(0)).current,ring3=useRef(new Animated.Value(0)).current,slideUp=useRef(new Animated.Value(30)).current;
  const confetti=useRef([...Array(12)].map(()=>({x:useRef(new Animated.Value(0)).current,y:useRef(new Animated.Value(0)).current,op:useRef(new Animated.Value(0)).current,rot:useRef(new Animated.Value(0)).current}))).current;
  useEffect(()=>{
    Animated.sequence([Animated.parallel([Animated.spring(scale,{toValue:1,tension:60,friction:6,useNativeDriver:true}),Animated.timing(opacity,{toValue:1,duration:300,useNativeDriver:true})]),Animated.spring(checkSc,{toValue:1,tension:80,friction:5,useNativeDriver:true}),Animated.parallel([Animated.stagger(80,[Animated.timing(ring1,{toValue:1,duration:500,useNativeDriver:true}),Animated.timing(ring2,{toValue:1,duration:500,useNativeDriver:true}),Animated.timing(ring3,{toValue:1,duration:500,useNativeDriver:true})]),Animated.timing(slideUp,{toValue:0,duration:400,useNativeDriver:true})])]).start();
    setTimeout(()=>{confetti.forEach((c,i)=>{const angle=(i/confetti.length)*Math.PI*2,dist=80+Math.random()*60;Animated.parallel([Animated.timing(c.x,{toValue:Math.cos(angle)*dist,duration:800,useNativeDriver:true}),Animated.timing(c.y,{toValue:Math.sin(angle)*dist-30,duration:800,useNativeDriver:true}),Animated.sequence([Animated.timing(c.op,{toValue:1,duration:200,useNativeDriver:true}),Animated.timing(c.op,{toValue:0,duration:600,useNativeDriver:true})]),Animated.timing(c.rot,{toValue:4,duration:800,useNativeDriver:true})]).start();});},400);
  },[]);
  const ringStyle=(anim,size,col)=>({position:"absolute",width:size,height:size,borderRadius:size/2,borderWidth:1.5,borderColor:col,opacity:anim.interpolate({inputRange:[0,1],outputRange:[0.6,0]}),transform:[{scale:anim.interpolate({inputRange:[0,1],outputRange:[0.5,1.6]})}]});
  const CONFETTI_COLORS=[C.gold,C.green,C.blue,C.amber,"#FF6B9D","#A78BFA"];
  const CONFETTI_SHAPES=["■","●","▲","★","◆"];
  return(
    <ScrollView contentContainerStyle={{padding:28,alignItems:"center",paddingTop:40}}>
      <Animated.View style={{alignItems:"center",justifyContent:"center",marginBottom:30,opacity,transform:[{scale}]}}>
        <Animated.View style={ringStyle(ring1,160,C.gold+"88")}/><Animated.View style={ringStyle(ring2,120,C.gold+"66")}/><Animated.View style={ringStyle(ring3,90,C.gold+"44")}/>
        {confetti.map((c,i)=>(
          <Animated.View key={i} style={{position:"absolute",opacity:c.op,transform:[{translateX:c.x},{translateY:c.y},{rotate:c.rot.interpolate({inputRange:[0,4],outputRange:["0deg","720deg"]})}]}}>
            <Text style={{fontSize:12,color:CONFETTI_COLORS[i%CONFETTI_COLORS.length]}}>{CONFETTI_SHAPES[i%CONFETTI_SHAPES.length]}</Text>
          </Animated.View>
        ))}
        <View style={{width:90,height:90,borderRadius:45,backgroundColor:C.greenDim,borderWidth:2.5,borderColor:C.green+"66",alignItems:"center",justifyContent:"center",shadowColor:C.green,shadowOpacity:0.4,shadowRadius:20,elevation:10}}>
          <Animated.Text style={{fontSize:38,transform:[{scale:checkSc}]}}>✓</Animated.Text>
        </View>
      </Animated.View>
      <Animated.View style={{alignItems:"center",opacity,transform:[{translateY:slideUp}]}}>
        <Text style={{fontSize:11,color:C.gold,letterSpacing:3,textTransform:"uppercase",marginBottom:8}}>Booking Confirmed</Text>
        <Text style={{fontSize:28,fontWeight:"400",color:C.text,textAlign:"center",lineHeight:36,marginBottom:6}}>{"You're all "}<Text style={{color:C.gold,fontStyle:"italic"}}>set!</Text></Text>
        <Text style={{fontSize:13,color:C.sub,textAlign:"center",lineHeight:22,maxWidth:280,marginBottom:28}}>Your shoot with <Text style={{color:C.text,fontWeight:"600"}}>{booking?.photog}</Text> on <Text style={{color:C.gold}}>{booking?.date}</Text> is locked in.</Text>
      </Animated.View>
      <Animated.View style={{width:"100%",opacity,transform:[{translateY:slideUp}]}}>
        <View style={{backgroundColor:C.card,borderWidth:1.5,borderColor:C.gold+"33",borderRadius:18,padding:20,marginBottom:22,overflow:"hidden"}}>
          <View style={{position:"absolute",top:0,left:0,right:0,height:3,backgroundColor:C.gold,borderTopLeftRadius:18,borderTopRightRadius:18}}/>
          <View style={{marginTop:8}}>
            {[{label:"Photographer",val:booking?.photog,icon:"📸"},{label:"Date",val:booking?.date,icon:"📅"},{label:"Shoot Type",val:booking?.type,icon:"🎬"},{label:"Duration",val:`${booking?.hours} hours`,icon:"⏱"},{label:"Total",val:`PKR ${booking?.amount?.toLocaleString()}`,icon:"💰"},{label:"Payment",val:"Offline · Cash / Transfer",icon:"💳"}].map((r,i)=>(
              <View key={r.label} style={{flexDirection:"row",alignItems:"center",paddingVertical:10,borderBottomWidth:i<5?1:0,borderBottomColor:C.border}}>
                <Text style={{fontSize:14,marginRight:10}}>{r.icon}</Text>
                <Text style={{fontSize:12,color:C.sub,flex:1}}>{r.label}</Text>
                <Text style={{fontSize:12,fontWeight:"700",color:r.label==="Total"?C.gold:C.text,maxWidth:160,textAlign:"right"}}>{r.val}</Text>
              </View>
            ))}
          </View>
        </View>
        <View style={{backgroundColor:C.greenDim,borderWidth:1,borderColor:C.green+"44",borderRadius:14,padding:14,marginBottom:18,flexDirection:"row",gap:12,alignItems:"center"}}>
          <Text style={{fontSize:18}}>🔒</Text>
          <View style={{flex:1}}>
            <Text style={{fontSize:12,color:C.green,fontWeight:"700",marginBottom:2}}>Slot Locked — No Overbooking</Text>
            <Text style={{fontSize:11,color:C.sub,lineHeight:17}}>This date is <Text style={{color:C.green}}>exclusively reserved</Text> for you.</Text>
          </View>
        </View>
        <TouchableOpacity onPress={onDone} style={{paddingVertical:15,borderRadius:14,backgroundColor:C.gold,alignItems:"center"}}>
          <Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>View My Bookings  →</Text>
        </TouchableOpacity>
      </Animated.View>
      <View style={{height:30}}/>
    </ScrollView>
  );
}

function AuthInput({ icon, placeholder, value, onChangeText, secureTextEntry, keyboardType, error }) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={{ marginBottom: error ? 6 : 14 }}>
      <View style={[{ flexDirection:"row", alignItems:"center", backgroundColor:C.card, borderRadius:13, borderWidth:1.5, paddingHorizontal:14, paddingVertical:2, gap:10 },{ borderColor: error ? C.red+"88" : focused ? C.gold+"88" : C.borderMid }]}>
        <Text style={{ fontSize:17, opacity:0.7 }}>{icon}</Text>
        <TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={C.dim} secureTextEntry={secureTextEntry} keyboardType={keyboardType||"default"} autoCapitalize="none" onFocus={()=>setFocused(true)} onBlur={()=>setFocused(false)} style={{ flex:1, color:C.text, fontSize:13, paddingVertical:13 }}/>
      </View>
      {error ? <Text style={{ fontSize:11, color:C.red, marginTop:4, marginLeft:4 }}>{error}</Text> : null}
    </View>
  );
}

function SplashScreen({ onDone }) {
  const ring1=useRef(new Animated.Value(0)).current,ring2=useRef(new Animated.Value(0)).current,ring3=useRef(new Animated.Value(0)).current,logoY=useRef(new Animated.Value(20)).current,logoOp=useRef(new Animated.Value(0)).current,tagOp=useRef(new Animated.Value(0)).current;
  useEffect(()=>{
    Animated.sequence([Animated.parallel([Animated.timing(logoOp,{toValue:1,duration:600,useNativeDriver:true}),Animated.timing(logoY,{toValue:0,duration:600,useNativeDriver:true})]),Animated.stagger(150,[Animated.timing(ring1,{toValue:1,duration:500,useNativeDriver:true}),Animated.timing(ring2,{toValue:1,duration:500,useNativeDriver:true}),Animated.timing(ring3,{toValue:1,duration:500,useNativeDriver:true})]),Animated.timing(tagOp,{toValue:1,duration:400,useNativeDriver:true})]).start(()=>setTimeout(onDone,800));
  },[]);
  const ringStyle=(anim,size)=>({width:size,height:size,borderRadius:size/2,borderWidth:1,borderColor:C.gold,position:"absolute",opacity:anim.interpolate({inputRange:[0,1],outputRange:[0,0.15]}),transform:[{scale:anim.interpolate({inputRange:[0,1],outputRange:[0.6,1]})}]});
  return(
    <View style={{flex:1,backgroundColor:C.bg,alignItems:"center",justifyContent:"center"}}>
      <Animated.View style={ringStyle(ring3,340)}/><Animated.View style={ringStyle(ring2,230)}/><Animated.View style={ringStyle(ring1,140)}/>
      <Animated.View style={{alignItems:"center",opacity:logoOp,transform:[{translateY:logoY}]}}>
        <View style={{width:76,height:76,borderRadius:38,backgroundColor:C.gold,alignItems:"center",justifyContent:"center",marginBottom:20,shadowColor:C.gold,shadowOpacity:0.5,shadowRadius:24,elevation:12}}>
          <Text style={{fontSize:34}}>📷</Text>
        </View>
        <Text style={{fontSize:34,fontWeight:"800",color:C.text,letterSpacing:-1,marginBottom:4}}>Snap<Text style={{color:C.gold,fontStyle:"italic"}}>Sphere</Text></Text>
        <Animated.Text style={{fontSize:11,color:C.sub,letterSpacing:3.5,textTransform:"uppercase",opacity:tagOp}}>Pakistan's Photography Marketplace</Animated.Text>
      </Animated.View>
      <Animated.View style={{position:"absolute",bottom:60,flexDirection:"row",gap:8,opacity:tagOp}}>
        {[0,1,2].map(i=><View key={i} style={{width:6,height:6,borderRadius:3,backgroundColor:i===1?C.gold:C.goldDim}}/>)}
      </Animated.View>
    </View>
  );
}

function LoginScreen({ onLogin, onGoRegister, onGoForgot }) {
  const [email,setEmail]=useState(""),[password,setPassword]=useState(""),[loading,setLoading]=useState(false),[errors,setErrors]=useState({}),[toast,setToast]=useState(null);
  const fadeIn=useRef(new Animated.Value(0)).current,slideY=useRef(new Animated.Value(24)).current;
  useEffect(()=>{Animated.parallel([Animated.timing(fadeIn,{toValue:1,duration:500,useNativeDriver:true}),Animated.timing(slideY,{toValue:0,duration:500,useNativeDriver:true})]).start();},[]);
  const validate=()=>{const e={};if(!email.trim())e.email="Email is required";else if(!/\S+@\S+\.\S+/.test(email))e.email="Enter a valid email";if(!password)e.password="Password is required";else if(password.length<6)e.password="At least 6 characters";setErrors(e);return Object.keys(e).length===0;};
  const handleLogin=async()=>{
    if(!validate()) return;
    setLoading(true);
    const apiResult = await API.login(email, password);
    if (apiResult.success) {
      setLoading(false);
      onLogin({ ...apiResult.data.user, activeRole: apiResult.data.user.role, token: apiResult.data.token });
      return;
    }
    setTimeout(()=>{
      const result=USER_STORE.login(email,password);
      setLoading(false);
      if(result.success){onLogin({...result.user,activeRole:result.user.role});}
      else{setErrors({general:result.error});setToast({message:result.error,type:"error"});}
    },900);
  };
  return(
    <KeyboardAvoidingView style={{flex:1,backgroundColor:C.bg}} behavior={Platform.OS==="ios"?"padding":undefined}>
      {toast&&<Toast message={toast.message} type={toast.type} onDone={()=>setToast(null)}/>}
      <ScrollView contentContainerStyle={{flexGrow:1}} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <View style={{height:160,alignItems:"center",justifyContent:"flex-end",paddingBottom:24,overflow:"hidden"}}>
          <View style={{position:"absolute",top:-60,width:260,height:260,borderRadius:130,backgroundColor:C.gold+"0D",borderWidth:1,borderColor:C.gold+"1A"}}/>
          <View style={{width:54,height:54,borderRadius:27,backgroundColor:C.gold,alignItems:"center",justifyContent:"center",shadowColor:C.gold,shadowOpacity:0.4,shadowRadius:16,elevation:8}}><Text style={{fontSize:24}}>📷</Text></View>
        </View>
        <Animated.View style={{paddingHorizontal:24,opacity:fadeIn,transform:[{translateY:slideY}]}}>
          <Text style={{fontSize:28,fontWeight:"800",color:C.text,letterSpacing:-0.8,marginBottom:4}}>Welcome back</Text>
          <Text style={{fontSize:13,color:C.sub,marginBottom:28}}>Sign in to your <Text style={{color:C.gold}}>SnapSphere</Text> account</Text>
          {errors.general&&<View style={{backgroundColor:C.redDim,borderWidth:1,borderColor:C.red+"44",borderRadius:10,padding:12,marginBottom:14}}><Text style={{fontSize:12,color:C.red}}>⚠  {errors.general}</Text></View>}
          <View style={{backgroundColor:C.blueDim,borderWidth:1,borderColor:C.blue+"33",borderRadius:10,padding:12,marginBottom:18}}>
            <Text style={{fontSize:11,color:C.blue}}>💡 Demo: demo@snapsphere.pk / demo123</Text>
          </View>
          <AuthInput icon="✉️" placeholder="Email address" value={email} onChangeText={v=>{setEmail(v);setErrors(p=>({...p,email:null,general:null}));}} keyboardType="email-address" error={errors.email}/>
          <AuthInput icon="🔒" placeholder="Password" value={password} onChangeText={v=>{setPassword(v);setErrors(p=>({...p,password:null,general:null}));}} secureTextEntry error={errors.password}/>
          <TouchableOpacity onPress={onGoForgot} style={{alignSelf:"flex-end",marginBottom:22,marginTop:-4}}><Text style={{fontSize:12,color:C.gold}}>Forgot password?</Text></TouchableOpacity>
          <TouchableOpacity onPress={handleLogin} disabled={loading} style={{paddingVertical:15,borderRadius:13,backgroundColor:C.gold,alignItems:"center",marginBottom:14,opacity:loading?0.7:1}}>
            <Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>{loading?"Signing in...":"Sign In  →"}</Text>
          </TouchableOpacity>
          <View style={{flexDirection:"row",justifyContent:"center",paddingBottom:32}}>
            <Text style={{fontSize:13,color:C.sub}}>Don't have an account? </Text>
            <TouchableOpacity onPress={onGoRegister}><Text style={{fontSize:13,color:C.gold,fontWeight:"700"}}>Create one</Text></TouchableOpacity>
          </View>
        </Animated.View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function RegisterScreen({ onRegister, onGoLogin }) {
  const [step,setStep]=useState(1);const[name,setName]=useState("");const[email,setEmail]=useState("");const[phone,setPhone]=useState("");const[city,setCity]=useState("");const[password,setPassword]=useState("");const[confirm,setConfirm]=useState("");const[role,setRole]=useState("buyer");const[loading,setLoading]=useState(false);const[errors,setErrors]=useState({});const[agreed,setAgreed]=useState(false);const[toast,setToast]=useState(null);
  const clearErr=(field)=>setErrors(p=>({...p,[field]:null}));
  const validateStep1=()=>{const e={};if(!name.trim())e.name="Full name is required";else if(name.trim().length<3)e.name="Min 3 characters";if(!email.trim())e.email="Email is required";else if(!/\S+@\S+\.\S+/.test(email))e.email="Enter a valid email";if(!phone.trim())e.phone="Phone is required";else if(!/^03[0-9]{9}$/.test(phone.replace(/\s/g,"")))e.phone="e.g. 03001234567";if(!password)e.password="Password is required";else if(password.length<6)e.password="Min 6 characters";if(!confirm)e.confirm="Please confirm";else if(password!==confirm)e.confirm="Passwords don't match";setErrors(e);return Object.keys(e).length===0;};
  const handleRegister=()=>{const e={};if(!city)e.city="Please select your city";if(!agreed)e.agree="You must accept the terms";setErrors(e);if(Object.keys(e).length>0)return;setLoading(true);setTimeout(()=>{const result=USER_STORE.register({name:name.trim(),email:email.trim().toLowerCase(),phone,city,password,role});setLoading(false);if(result.success){setToast({message:"Account created! Please sign in.",type:"success"});setTimeout(()=>onRegister(),1200);}else{setToast({message:result.error,type:"error"});}},1000);};
  const CITIES=["Islamabad","Rawalpindi","Lahore","Karachi","Peshawar","Quetta","Multan","Faisalabad"];
  const ROLES=[{id:"buyer",icon:"🔍",label:"Client / Buyer",desc:"Book photographers"},{id:"photographer",icon:"📸",label:"Photographer",desc:"List your services"}];
  const strength=()=>{if(!password)return{bars:0,label:"",color:C.border};if(password.length<4)return{bars:1,label:"Too weak",color:C.red};if(password.length<6)return{bars:2,label:"Weak",color:C.red};if(password.length<8)return{bars:3,label:"Fair",color:C.amber};if(/[!@#$%^&*]/.test(password))return{bars:4,label:"Strong",color:C.green};return{bars:3,label:"Good",color:C.amber};};
  const s=strength();
  return(
    <KeyboardAvoidingView style={{flex:1,backgroundColor:C.bg}} behavior={Platform.OS==="ios"?"padding":undefined}>
      {toast&&<Toast message={toast.message} type={toast.type} onDone={()=>setToast(null)}/>}
      <ScrollView contentContainerStyle={{flexGrow:1}} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <View style={{paddingHorizontal:24,paddingTop:52,paddingBottom:20}}>
          <TouchableOpacity onPress={onGoLogin} style={{alignSelf:"flex-start",flexDirection:"row",alignItems:"center",gap:6,marginBottom:24}}><Text style={{color:C.sub,fontSize:18}}>←</Text><Text style={{color:C.sub,fontSize:12}}>Back to login</Text></TouchableOpacity>
          <View style={{flexDirection:"row",gap:6,marginBottom:24}}>{[1,2].map(st=><View key={st} style={{flex:1,height:3,borderRadius:2,backgroundColor:step>=st?C.gold:C.border}}/>)}</View>
          <Text style={{fontSize:10,color:C.gold,letterSpacing:1.8,textTransform:"uppercase",marginBottom:6}}>Step {step} of 2</Text>
          <Text style={{fontSize:26,fontWeight:"800",color:C.text,letterSpacing:-0.6,marginBottom:4}}>{step===1?"Create your account":"Choose your role"}</Text>
        </View>
        <View style={{paddingHorizontal:24}}>
          {step===1&&(<View>
            <AuthInput icon="👤" placeholder="Full name" value={name} onChangeText={v=>{setName(v);clearErr("name")}} error={errors.name}/>
            <AuthInput icon="✉️" placeholder="Email address" value={email} onChangeText={v=>{setEmail(v);clearErr("email")}} keyboardType="email-address" error={errors.email}/>
            <AuthInput icon="📱" placeholder="Phone (03001234567)" value={phone} onChangeText={v=>{setPhone(v);clearErr("phone")}} keyboardType="phone-pad" error={errors.phone}/>
            <AuthInput icon="🔒" placeholder="Password (min 6)" value={password} onChangeText={v=>{setPassword(v);clearErr("password")}} secureTextEntry error={errors.password}/>
            {password.length>0&&(<View style={{marginTop:-8,marginBottom:14}}><View style={{flexDirection:"row",gap:4,marginBottom:4}}>{[1,2,3,4].map(i=><View key={i} style={{flex:1,height:3,borderRadius:2,backgroundColor:i<=s.bars?s.color:C.border}}/>)}</View><Text style={{fontSize:10,color:s.color}}>{s.label}</Text></View>)}
            <AuthInput icon="🔒" placeholder="Confirm password" value={confirm} onChangeText={v=>{setConfirm(v);clearErr("confirm")}} secureTextEntry error={errors.confirm}/>
            <TouchableOpacity onPress={()=>{if(!validateStep1())return;setStep(2);}} style={{paddingVertical:15,borderRadius:13,backgroundColor:C.gold,alignItems:"center",marginTop:6,marginBottom:28}}><Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>Continue  →</Text></TouchableOpacity>
          </View>)}
          {step===2&&(<View>
            <View style={{gap:12,marginBottom:22}}>{ROLES.map(r=>(<TouchableOpacity key={r.id} onPress={()=>setRole(r.id)} style={{flexDirection:"row",alignItems:"center",gap:14,padding:16,borderRadius:14,borderWidth:1.5,borderColor:role===r.id?C.gold:C.border,backgroundColor:role===r.id?C.gold+"10":C.card}}><Text style={{fontSize:22}}>{r.icon}</Text><View style={{flex:1}}><Text style={{fontSize:14,fontWeight:"700",color:role===r.id?C.text:C.sub}}>{r.label}</Text><Text style={{fontSize:11,color:C.dim}}>{r.desc}</Text></View><View style={{width:20,height:20,borderRadius:10,borderWidth:2,borderColor:role===r.id?C.gold:C.border,backgroundColor:role===r.id?C.gold:"transparent",alignItems:"center",justifyContent:"center"}}>{role===r.id&&<View style={{width:8,height:8,borderRadius:4,backgroundColor:C.bg}}/>}</View></TouchableOpacity>))}</View>
            <Text style={{fontSize:10,color:C.sub,letterSpacing:1.5,textTransform:"uppercase",marginBottom:10}}>Your city *</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom:4}}>{CITIES.map(c=>(<TouchableOpacity key={c} onPress={()=>{setCity(c);clearErr("city")}} style={{paddingHorizontal:14,paddingVertical:8,borderRadius:20,marginRight:8,backgroundColor:city===c?C.gold:C.card,borderWidth:1,borderColor:city===c?C.gold:C.border}}><Text style={{fontSize:12,fontWeight:"600",color:city===c?C.bg:C.sub}}>{c}</Text></TouchableOpacity>))}</ScrollView>
            {errors.city&&<Text style={{fontSize:11,color:C.red,marginBottom:10,marginTop:4}}>{errors.city}</Text>}
            <View style={{height:14}}/>
            <TouchableOpacity onPress={()=>{setAgreed(!agreed);clearErr("agree")}} style={{flexDirection:"row",alignItems:"flex-start",gap:12,marginBottom:4}}><View style={{width:20,height:20,borderRadius:5,borderWidth:1.5,marginTop:1,borderColor:agreed?C.gold:C.border,backgroundColor:agreed?C.gold:"transparent",alignItems:"center",justifyContent:"center",flexShrink:0}}>{agreed&&<Text style={{fontSize:11,color:C.bg,fontWeight:"800"}}>✓</Text>}</View><Text style={{flex:1,fontSize:12,color:C.sub,lineHeight:19}}>I agree to SnapSphere's <Text style={{color:C.gold}}>Terms</Text> and <Text style={{color:C.gold}}>Privacy Policy</Text></Text></TouchableOpacity>
            {errors.agree&&<Text style={{fontSize:11,color:C.red,marginBottom:8,marginLeft:32}}>{errors.agree}</Text>}
            <TouchableOpacity onPress={handleRegister} disabled={loading} style={{paddingVertical:15,borderRadius:13,backgroundColor:C.gold,alignItems:"center",marginTop:16,marginBottom:28,opacity:loading?0.7:1}}><Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>{loading?"Creating...":"Create Account  ✓"}</Text></TouchableOpacity>
            <View style={{flexDirection:"row",justifyContent:"center",paddingBottom:32}}><Text style={{fontSize:13,color:C.sub}}>Already have an account? </Text><TouchableOpacity onPress={onGoLogin}><Text style={{fontSize:13,color:C.gold,fontWeight:"700"}}>Sign in</Text></TouchableOpacity></View>
          </View>)}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function ForgotPasswordScreen({ onGoLogin }) {
  const [step,setStep]=useState(1);const[email,setEmail]=useState("");const[otp,setOtp]=useState(["","","","","",""]);const[newPass,setNewPass]=useState("");const[confirm,setConfirm]=useState("");const[loading,setLoading]=useState(false);const[error,setError]=useState("");
  const otpRefs=useRef([...Array(6)].map(()=>null));
  const sendOtp=()=>{if(!email.trim()||!/\S+@\S+\.\S+/.test(email)){setError("Enter a valid email");return;}const exists=USER_STORE.users.find(u=>u.email.toLowerCase()===email.toLowerCase());if(!exists){setError("No account found with that email.");return;}setError("");setLoading(true);setTimeout(()=>{setLoading(false);setStep(2);},1200);};
  const verifyOtp=()=>{if(otp.join("").length<6){setError("Enter all 6 digits");return;}setError("");setLoading(true);setTimeout(()=>{setLoading(false);setStep(3);},1000);};
  const resetPassword=()=>{if(!newPass||newPass.length<6){setError("Min 6 characters");return;}if(newPass!==confirm){setError("Passwords don't match");return;}setError("");setLoading(true);setTimeout(()=>{const user=USER_STORE.users.find(u=>u.email.toLowerCase()===email.toLowerCase());if(user)user.password=newPass;setLoading(false);setStep(4);},1200);};
  const handleOtpChange=(val,idx)=>{const next=[...otp];next[idx]=val.replace(/[^0-9]/g,"").slice(-1);setOtp(next);if(val&&idx<5)otpRefs.current[idx+1]?.focus();if(!val&&idx>0)otpRefs.current[idx-1]?.focus();};
  return(
    <KeyboardAvoidingView style={{flex:1,backgroundColor:C.bg}} behavior={Platform.OS==="ios"?"padding":undefined}>
      <ScrollView contentContainerStyle={{flexGrow:1}} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <View style={{paddingHorizontal:24,paddingTop:52,paddingBottom:24}}>
          <TouchableOpacity onPress={onGoLogin} style={{alignSelf:"flex-start",flexDirection:"row",alignItems:"center",gap:6,marginBottom:24}}><Text style={{color:C.sub,fontSize:18}}>←</Text><Text style={{color:C.sub,fontSize:12}}>Back to login</Text></TouchableOpacity>
          <View style={{width:56,height:56,borderRadius:28,backgroundColor:C.gold+"18",borderWidth:1.5,borderColor:C.gold+"44",alignItems:"center",justifyContent:"center",marginBottom:16}}><Text style={{fontSize:26}}>{step===1?"✉️":step===2?"🔢":step===3?"🔒":"✅"}</Text></View>
          <Text style={{fontSize:24,fontWeight:"800",color:C.text,marginBottom:6}}>{step===1?"Forgot password?":step===2?"Check your email":step===3?"New password":"Password reset!"}</Text>
        </View>
        <View style={{paddingHorizontal:24}}>
          {error?<View style={{backgroundColor:C.redDim,borderWidth:1,borderColor:C.red+"44",borderRadius:10,padding:12,marginBottom:14}}><Text style={{fontSize:12,color:C.red}}>⚠  {error}</Text></View>:null}
          {step===1&&<View><AuthInput icon="✉️" placeholder="Your email" value={email} onChangeText={v=>{setEmail(v);setError("")}} keyboardType="email-address"/><TouchableOpacity onPress={sendOtp} disabled={loading} style={{paddingVertical:15,borderRadius:13,backgroundColor:C.gold,alignItems:"center",opacity:loading?0.7:1}}><Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>{loading?"Sending...":"Send Reset Code  →"}</Text></TouchableOpacity></View>}
          {step===2&&<View><View style={{flexDirection:"row",gap:8,marginBottom:22,justifyContent:"center"}}>{otp.map((digit,i)=><TextInput key={i} ref={ref=>otpRefs.current[i]=ref} value={digit} onChangeText={val=>handleOtpChange(val,i)} keyboardType="number-pad" maxLength={1} style={{width:44,height:52,borderRadius:12,textAlign:"center",fontSize:20,fontWeight:"800",color:C.text,backgroundColor:C.card,borderWidth:1.5,borderColor:digit?C.gold:C.borderMid}}/>)}</View><TouchableOpacity onPress={verifyOtp} disabled={loading} style={{paddingVertical:15,borderRadius:13,backgroundColor:C.gold,alignItems:"center",opacity:loading?0.7:1}}><Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>{loading?"Verifying...":"Verify Code  →"}</Text></TouchableOpacity></View>}
          {step===3&&<View><AuthInput icon="🔒" placeholder="New password" value={newPass} onChangeText={v=>{setNewPass(v);setError("")}} secureTextEntry/><AuthInput icon="🔒" placeholder="Confirm" value={confirm} onChangeText={v=>{setConfirm(v);setError("")}} secureTextEntry/><TouchableOpacity onPress={resetPassword} disabled={loading} style={{paddingVertical:15,borderRadius:13,backgroundColor:C.gold,alignItems:"center",opacity:loading?0.7:1}}><Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>{loading?"Resetting...":"Reset Password  ✓"}</Text></TouchableOpacity></View>}
          {step===4&&<View style={{alignItems:"center",paddingTop:12}}><View style={{width:80,height:80,borderRadius:40,backgroundColor:C.greenDim,borderWidth:2,borderColor:C.green+"44",alignItems:"center",justifyContent:"center",marginBottom:20}}><Text style={{fontSize:36,color:C.green}}>✓</Text></View><TouchableOpacity onPress={onGoLogin} style={{paddingVertical:15,paddingHorizontal:40,borderRadius:13,backgroundColor:C.gold,alignItems:"center"}}><Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>Go to Sign In  →</Text></TouchableOpacity></View>}
          <View style={{height:32}}/>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function useRecommendations(currentUser) {
  const [recommendations, setRecommendations] = useState([]);
  const [recType,          setRecType]         = useState("popular");
  const [loading,          setLoading]         = useState(true);
  const [apiConnected,     setApiConnected]    = useState(false);

  useEffect(() => {
    if (!currentUser) return;
    setLoading(true);

    const loadRecommendations = async () => {
      const apiResult = await API.getRecommendations(currentUser.id, 6);

      if (apiResult.success) {
        const mapped = apiResult.data.recommendations
          .map(rec => {
            const photog = PHOTOGRAPHERS.find(p => p.apiId === rec.photographer_id);
            return photog ? { ...photog, predictedRating: rec.predicted_rating.toFixed(2), isPersonalized: apiResult.data.type === "personalized" } : null;
          })
          .filter(Boolean)
          .slice(0, 6);

        setRecommendations(mapped.length > 0 ? mapped : getFallback());
        setRecType(apiResult.data.type);
        setApiConnected(true);
      } else {
        const userBookings = BOOKINGS_STORE.getUserBookings(currentUser.id);
        const local = getLocalRecommendations(currentUser.id, userBookings);
        setRecommendations(local.photographers.slice(0, 6));
        setRecType(local.type);
        setApiConnected(false);
      }

      setLoading(false);
    };

    const getFallback = () => {
      const userBookings = BOOKINGS_STORE.getUserBookings(currentUser.id);
      return getLocalRecommendations(currentUser.id, userBookings).photographers.slice(0, 6);
    };

    loadRecommendations();
  }, [currentUser?.id]);

  return { recommendations, recType, loading, apiConnected };
}

function HomeScreen({ onNavigate, onViewPhotog, currentUser, onSwitchRole, onShowNotifs }) {
  const featured = PHOTOGRAPHERS[0];
  const nearby   = PHOTOGRAPHERS.slice(1, 4);
  const initial  = currentUser?.name?.[0]?.toUpperCase() || "U";
  const isPhotog = currentUser?.activeRole === "photographer";

  const { recommendations, recType, loading: recLoading, apiConnected } = useRecommendations(currentUser);

  return (
    <ScrollView style={{ flex:1 }} showsVerticalScrollIndicator={false}>
      <View style={{ padding:20, paddingTop:24, flexDirection:"row", justifyContent:"space-between", alignItems:"center" }}>
        <View style={{ flex:1 }}>
          <Text style={{ fontSize:11, letterSpacing:1.8, color:C.gold, textTransform:"uppercase", marginBottom:4 }}>Good day ✦</Text>
          <Text style={{ fontSize:22, fontWeight:"400", color:C.text, lineHeight:30 }}>
            {isPhotog ? "Your " : "Find Your\n"}<Text style={{ color:C.gold, fontStyle:"italic" }}>{isPhotog ? "Dashboard" : "Perfect"}</Text>{isPhotog ? " Hub" : " Photographer"}
          </Text>
        </View>
        <View style={{ alignItems:"flex-end", gap:10 }}>
          <View style={{ flexDirection:"row", alignItems:"center", gap:8 }}>
            <NotificationBell userId={currentUser?.id} onPress={onShowNotifs} />
            <View style={{ width:42, height:42, borderRadius:21, backgroundColor:C.gold, alignItems:"center", justifyContent:"center" }}>
              <Text style={{ fontSize:16, color:C.bg, fontWeight:"800" }}>{initial}</Text>
            </View>
          </View>
          <RoleSwitcher currentUser={currentUser} onSwitch={onSwitchRole} />
        </View>
      </View>

      {isPhotog ? (
        <View style={{ padding:20, paddingTop:4 }}>
          <View style={{ backgroundColor:C.card, borderWidth:1.5, borderColor:C.gold+"33", borderRadius:18, padding:18, marginBottom:16 }}>
            <Text style={{ fontSize:13, color:C.sub, marginBottom:12 }}>📊 Your Quick Stats</Text>
            <View style={{ flexDirection:"row", gap:10 }}>
              {[{label:"Bookings",val:"48",color:C.gold},{label:"Earnings",val:"PKR 184k",color:C.green},{label:"Rating",val:"4.9★",color:C.amber}].map(s=>(
                <View key={s.label} style={{ flex:1, backgroundColor:C.bg+"44", borderRadius:12, padding:12, alignItems:"center" }}>
                  <Text style={{ fontSize:14, fontWeight:"800", color:s.color }}>{s.val}</Text>
                  <Text style={{ fontSize:9, color:C.sub, marginTop:3 }}>{s.label}</Text>
                </View>
              ))}
            </View>
          </View>
          <Text style={{ fontSize:14, fontWeight:"700", color:C.text, marginBottom:12 }}>Upcoming Shoots</Text>
          {[{date:"May 15",client:"Ahmad R.",type:"Wedding",amt:8500},{date:"May 20",client:"Sara K.",type:"Portrait",amt:6000}].map((b,i)=>(
            <View key={i} style={{ backgroundColor:C.card, borderWidth:1, borderColor:C.border, borderRadius:14, padding:14, marginBottom:10, flexDirection:"row", alignItems:"center", gap:12 }}>
              <View style={{ backgroundColor:C.gold+"18", borderRadius:10, padding:10 }}><Text style={{ fontSize:18 }}>📅</Text></View>
              <View style={{ flex:1 }}>
                <Text style={{ fontSize:13, fontWeight:"700", color:C.text }}>{b.type} · {b.client}</Text>
                <Text style={{ fontSize:11, color:C.sub, marginTop:2 }}>{b.date}</Text>
              </View>
              <Text style={{ fontSize:13, fontWeight:"700", color:C.gold }}>PKR {b.amt.toLocaleString()}</Text>
            </View>
          ))}
        </View>
      ) : (
        <View>
          <View style={{ marginHorizontal:20, marginBottom:20 }}>
            <View style={{ backgroundColor:C.card, borderWidth:1, borderColor:C.borderMid, borderRadius:14, padding:13, flexDirection:"row", alignItems:"center", gap:10 }}>
              <Text style={{ fontSize:15 }}>🔍</Text>
              <Text style={{ fontSize:13, color:C.dim, flex:1 }}>Search by style, city, occasion...</Text>
              <View style={{ backgroundColor:C.gold, borderRadius:8, paddingHorizontal:10, paddingVertical:4 }}>
                <Text style={{ fontSize:11, color:C.bg, fontWeight:"700" }}>AI</Text>
              </View>
            </View>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom:24 }} contentContainerStyle={{ paddingHorizontal:20, gap:8 }}>
            {["All","Wedding","Fashion","Events","Portrait","Nature","Corporate"].map((cat,i) => (
              <TouchableOpacity key={cat} style={{ paddingHorizontal:16, paddingVertical:7, borderRadius:20, backgroundColor:i===0?C.gold:C.card, borderWidth:1, borderColor:i===0?C.gold:C.border, marginRight:8 }}>
                <Text style={{ fontSize:11, fontWeight:"600", letterSpacing:0.6, color:i===0?C.bg:C.sub }}>{cat}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <View style={{ marginBottom:28 }}>
            <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"center", paddingHorizontal:20, marginBottom:14 }}>
              <View>
                <View style={{ flexDirection:"row", alignItems:"center", gap:8, marginBottom:4 }}>
                  <Text style={{ fontSize:16, fontWeight:"700", color:C.text }}>
                    {recType === "personalized" ? "✦ Picked For You" : "🏆 Top Photographers"}
                  </Text>
                  {apiConnected && (
                    <View style={{ backgroundColor:C.green+"22", paddingHorizontal:6, paddingVertical:2, borderRadius:6, borderWidth:1, borderColor:C.green+"44" }}>
                      <Text style={{ fontSize:8, color:C.green, fontWeight:"700" }}>LIVE</Text>
                    </View>
                  )}
                </View>
                <Text style={{ fontSize:11, color:C.sub }}>
                  {recType === "personalized"
                    ? "Based on your booking history · SVD Model"
                    : "Highest-rated in your area · Bayesian Score"}
                </Text>
              </View>
              <TouchableOpacity onPress={() => onNavigate("Explore")}>
                <Text style={{ fontSize:11, color:C.gold }}>See all →</Text>
              </TouchableOpacity>
            </View>

            {recLoading ? (
              <View style={{ alignItems:"center", paddingVertical:30 }}>
                <ActivityIndicator color={C.gold} size="small" />
                <Text style={{ fontSize:11, color:C.sub, marginTop:8 }}>Loading AI recommendations...</Text>
              </View>
            ) : (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal:20, gap:12 }}>
                {recommendations.map((p) => (
                  <TouchableOpacity
                    key={p.id}
                    onPress={() => onViewPhotog(p)}
                    style={{ width:170, backgroundColor:C.card, borderWidth:1, borderColor: p.isPersonalized ? C.gold+"33" : C.border, borderRadius:16, padding:14, borderTopWidth:2, borderTopColor: p.isPersonalized ? C.gold : C.blue }}>
                    <View style={{ marginBottom:10 }}>
                      <AIBadge score={p.predictedRating} isPersonalized={p.isPersonalized} />
                    </View>
                    <Avatar initials={p.img} color={p.color} size={44} />
                    <Text style={{ fontSize:14, fontWeight:"700", color:C.text, marginTop:10, marginBottom:2 }}>{p.name}</Text>
                    <Text style={{ fontSize:10, color:C.sub, marginBottom:8 }}>{p.role}</Text>
                    <View style={{ flexDirection:"row", alignItems:"center", gap:4, marginBottom:10 }}>
                      <Stars rating={p.rating} />
                      <Text style={{ fontSize:10, color:C.gold, fontWeight:"700" }}>{p.rating}</Text>
                    </View>
                    <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"center" }}>
                      <Text style={{ fontSize:12, fontWeight:"800", color:C.gold }}>
                        PKR {(p.price/1000).toFixed(0)}k
                      </Text>
                      <View style={{ paddingHorizontal:8, paddingVertical:3, borderRadius:6, backgroundColor:p.avail?C.greenDim:C.redDim }}>
                        <Text style={{ fontSize:9, fontWeight:"700", color:p.avail?C.green:C.red }}>
                          {p.avail ? "Free" : "Busy"}
                        </Text>
                      </View>
                    </View>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}

            <View style={{ flexDirection:"row", alignItems:"center", gap:6, paddingHorizontal:20, marginTop:10 }}>
              <View style={{ width:6, height:6, borderRadius:3, backgroundColor: apiConnected ? C.green : C.amber }} />
              <Text style={{ fontSize:10, color:C.dim }}>
                {apiConnected
                  ? "Connected to Django recommendation API"
                  : "Offline mode · Set DJANGO_BASE_URL to connect"}
              </Text>
            </View>
          </View>

          <View style={{ paddingHorizontal:20, marginBottom:28 }}>
            <SectionHeader title="✦ Featured This Week" />
            <TouchableOpacity onPress={() => onViewPhotog(featured)} style={{ backgroundColor:C.card, borderWidth:1, borderColor:C.gold+"33", borderRadius:18, padding:20 }}>
              <View style={{ flexDirection:"row", gap:14, alignItems:"center", marginBottom:16 }}>
                <Avatar initials={featured.img} color={featured.color} size={60} />
                <View>
                  <Text style={{ fontSize:19, fontWeight:"700", color:C.text }}>{featured.name}</Text>
                  <Text style={{ fontSize:12, color:C.sub, marginTop:2 }}>{featured.role}</Text>
                  <View style={{ flexDirection:"row", alignItems:"center", gap:6, marginTop:5 }}>
                    <Stars rating={featured.rating} />
                    <Text style={{ fontSize:12, color:C.gold, fontWeight:"700" }}>{featured.rating}</Text>
                  </View>
                </View>
              </View>
              <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"center" }}>
                <Text style={{ fontSize:24, fontWeight:"800", color:C.gold }}>PKR {featured.price.toLocaleString()}<Text style={{ fontSize:11, color:C.dim, fontWeight:"400" }}>/day</Text></Text>
                <View style={{ backgroundColor:C.gold, borderRadius:10, paddingHorizontal:18, paddingVertical:8 }}>
                  <Text style={{ fontSize:12, fontWeight:"700", color:C.bg }}>View Profile</Text>
                </View>
              </View>
            </TouchableOpacity>
          </View>

          <SectionHeader title="Near You · Islamabad" action="See all" onAction={() => onNavigate("Explore")} />
          <View style={{ paddingHorizontal:20, gap:10, marginBottom:20 }}>
            {nearby.map(p => (
              <TouchableOpacity key={p.id} onPress={() => onViewPhotog(p)} style={{ backgroundColor:C.card, borderWidth:1, borderColor:C.border, borderRadius:14, padding:14, flexDirection:"row", alignItems:"center", gap:12, borderLeftWidth:3, borderLeftColor:p.color }}>
                <Avatar initials={p.img} color={p.color} size={44} />
                <View style={{ flex:1 }}>
                  <Text style={{ fontSize:14, fontWeight:"700", color:C.text }}>{p.name}</Text>
                  <Text style={{ fontSize:11, color:C.sub, marginTop:1 }}>{p.role} · {p.city}</Text>
                </View>
                <View style={{ alignItems:"flex-end" }}>
                  <Text style={{ fontSize:14, fontWeight:"800", color:C.gold }}>PKR {(p.price/1000).toFixed(0)}k</Text>
                  <Stars rating={p.rating} />
                </View>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}
      <View style={{ height:20 }} />
    </ScrollView>
  );
}

function ExploreScreen({ onViewPhotog, currentUser }) {
  const [filter,  setFilter]  = useState("All");
  const [sortBy,  setSortBy]  = useState("AI Score");
  const [search,  setSearch]  = useState("");
  const { recommendations, recType, loading: recLoading } = useRecommendations(currentUser);

  const cats = ["All","Wedding","Fashion","Commercial","Event","Nature","Family","Architecture"];

  const enriched = PHOTOGRAPHERS.map(p => {
    const rec = recommendations.find(r => r.id === p.id);
    return { ...p, predictedRating: rec ? parseFloat(rec.predictedRating) : p.rating, isRecommended: !!rec };
  });

  const list = enriched
    .filter(p => filter==="All" || p.tags.some(t => t===filter))
    .filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.city.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sortBy==="AI Score") return b.predictedRating - a.predictedRating;
      if (sortBy==="Rating")   return b.rating - a.rating;
      return a.price - b.price;
    });

  return (
    <ScrollView style={{ flex:1 }} showsVerticalScrollIndicator={false}>
      <View style={{ padding:20, paddingTop:24 }}>
        <Text style={{ fontSize:26, fontWeight:"400", color:C.text, marginBottom:16 }}>Explore <Text style={{ color:C.gold, fontStyle:"italic" }}>Photographers</Text></Text>
        <View style={{ backgroundColor:C.card, borderWidth:1, borderColor:C.borderMid, borderRadius:12, padding:11, flexDirection:"row", alignItems:"center", gap:10, marginBottom:14 }}>
          <Text style={{ fontSize:14 }}>🔍</Text>
          <TextInput value={search} onChangeText={setSearch} placeholder="Name, city, specialty..." placeholderTextColor={C.dim} style={{ flex:1, color:C.text, fontSize:13 }} />
          {!!search && <TouchableOpacity onPress={() => setSearch("")}><Text style={{ color:C.dim, fontSize:16 }}>✕</Text></TouchableOpacity>}
        </View>
        <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
          <Text style={{ fontSize:11, color:C.sub }}>{list.length} photographers</Text>
          <View style={{ flexDirection:"row", gap:6 }}>
            {["AI Score","Rating","Price"].map(s => (
              <TouchableOpacity key={s} onPress={() => setSortBy(s)} style={{ paddingHorizontal:10, paddingVertical:4, borderRadius:8, backgroundColor:sortBy===s?C.gold:C.card, borderWidth:1, borderColor:sortBy===s?C.gold:C.border }}>
                <Text style={{ fontSize:10, fontWeight:"600", color:sortBy===s?C.bg:C.sub }}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom:18 }} contentContainerStyle={{ paddingHorizontal:20 }}>
        {cats.map(c => (
          <TouchableOpacity key={c} onPress={() => setFilter(c)} style={{ paddingHorizontal:14, paddingVertical:6, borderRadius:20, marginRight:7, backgroundColor:filter===c?C.gold:C.card, borderWidth:1, borderColor:filter===c?C.gold:C.border }}>
            <Text style={{ fontSize:11, fontWeight:"600", color:filter===c?C.bg:C.sub }}>{c}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <View style={{ paddingHorizontal:20, gap:12 }}>
        {list.map(p => (
          <TouchableOpacity key={p.id} onPress={() => onViewPhotog(p)} style={{ backgroundColor:C.card, borderWidth:1, borderColor: p.isRecommended ? C.gold+"44" : C.border, borderRadius:16, padding:16 }}>
            <View style={{ flexDirection:"row", gap:12, alignItems:"flex-start" }}>
              <Avatar initials={p.img} color={p.color} size={50} />
              <View style={{ flex:1 }}>
                <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"flex-start" }}>
                  <View style={{ flex:1 }}>
                    <View style={{ flexDirection:"row", alignItems:"center", gap:8, flexWrap:"wrap" }}>
                      <Text style={{ fontSize:15, fontWeight:"700", color:C.text }}>{p.name}</Text>
                      {p.isRecommended && <AIBadge score={p.predictedRating.toFixed(2)} isPersonalized={recType==="personalized"} />}
                    </View>
                    <Text style={{ fontSize:11, color:C.sub, marginTop:1 }}>{p.role}</Text>
                  </View>
                  <View style={{ paddingHorizontal:9, paddingVertical:3, borderRadius:6, backgroundColor:p.avail?C.greenDim:C.redDim, borderWidth:1, borderColor:(p.avail?C.green:C.red)+"44" }}>
                    <Text style={{ fontSize:10, fontWeight:"700", color:p.avail?C.green:C.red }}>{p.avail?"Available":"Booked"}</Text>
                  </View>
                </View>
                <View style={{ flexDirection:"row", alignItems:"center", gap:8, marginTop:8 }}>
                  <Stars rating={p.rating} />
                  <Text style={{ fontSize:11, color:C.gold, fontWeight:"700" }}>{p.rating}</Text>
                  <Text style={{ fontSize:10, color:C.sub }}>📍 {p.city}</Text>
                </View>
              </View>
            </View>
            <View style={{ marginTop:12, paddingTop:12, borderTopWidth:1, borderTopColor:C.border, flexDirection:"row", justifyContent:"space-between", alignItems:"center" }}>
              <View style={{ flexDirection:"row", flexWrap:"wrap", gap:4 }}>
                {p.tags.map(t => <Badge key={t} label={t} color={C.sub} />)}
              </View>
              <Text style={{ fontSize:17, fontWeight:"800", color:C.gold }}>PKR {p.price.toLocaleString()}<Text style={{ fontSize:10, color:C.sub, fontWeight:"400" }}>/day</Text></Text>
            </View>
          </TouchableOpacity>
        ))}
      </View>
      <View style={{ height:20 }} />
    </ScrollView>
  );
}

function PortfolioGrid({ photogId }) {
  const photos = PORTFOLIO_PHOTOS[photogId] || [];
  const [lightbox, setLightbox] = useState(null);
  const fadeAnim  = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.88)).current;
  const openLightbox=(idx)=>{setLightbox(idx);Animated.parallel([Animated.timing(fadeAnim,{toValue:1,duration:220,useNativeDriver:true}),Animated.spring(scaleAnim,{toValue:1,tension:80,friction:7,useNativeDriver:true})]).start();};
  const closeLightbox=()=>{Animated.parallel([Animated.timing(fadeAnim,{toValue:0,duration:180,useNativeDriver:true}),Animated.timing(scaleAnim,{toValue:0.88,duration:180,useNativeDriver:true})]).start(()=>setLightbox(null));};
  const goNext=()=>setLightbox(i=>(i+1)%photos.length);
  const goPrev=()=>setLightbox(i=>(i-1+photos.length)%photos.length);
  return(
    <View>
      <View style={{flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
        <Text style={{fontSize:12,color:C.sub}}>{photos.length} photos · Tap to expand</Text>
        <View style={{flexDirection:"row",alignItems:"center",gap:5}}><View style={{width:8,height:8,borderRadius:4,backgroundColor:C.gold}}/><Text style={{fontSize:10,color:C.gold}}>Featured</Text></View>
      </View>
      <View style={{flexDirection:"row",flexWrap:"wrap",gap:8}}>
        {photos.map((photo,i)=>(
          <TouchableOpacity key={photo.id} onPress={()=>openLightbox(i)} activeOpacity={0.88} style={{height:photo.featured?200:120,width:photo.featured?"100%":"47%",borderRadius:14,overflow:"hidden",borderWidth:photo.featured?1.5:1,borderColor:photo.featured?C.gold+"55":C.border}}>
            <Image source={{uri:photo.uri}} style={{width:"100%",height:"100%"}} resizeMode="cover"/>
            <View style={{position:"absolute",bottom:0,left:0,right:0,height:56,backgroundColor:"#00000077"}}/>
            <View style={{position:"absolute",bottom:8,left:10,right:10,flexDirection:"row",alignItems:"center",justifyContent:"space-between"}}>
              <Text style={{fontSize:11,fontWeight:"600",color:"#fff"}}>{photo.label}</Text>
              {photo.featured&&<View style={{backgroundColor:C.gold,borderRadius:6,paddingHorizontal:7,paddingVertical:2}}><Text style={{fontSize:9,fontWeight:"800",color:C.bg}}>★ FEATURED</Text></View>}
            </View>
            <View style={{position:"absolute",top:8,right:8,width:26,height:26,borderRadius:8,backgroundColor:"#00000066",alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:12,color:"#fff"}}>⤢</Text></View>
          </TouchableOpacity>
        ))}
      </View>
      {lightbox!==null&&(
        <Modal transparent animationType="none" visible={lightbox!==null} onRequestClose={closeLightbox}>
          <Animated.View style={{flex:1,backgroundColor:"#000000EE",alignItems:"center",justifyContent:"center",opacity:fadeAnim}}>
            <TouchableOpacity onPress={closeLightbox} style={{position:"absolute",top:48,right:20,width:40,height:40,borderRadius:20,backgroundColor:"#ffffff22",alignItems:"center",justifyContent:"center",zIndex:10}}><Text style={{fontSize:18,color:"#fff"}}>✕</Text></TouchableOpacity>
            <View style={{position:"absolute",top:56,left:20,zIndex:10}}><Text style={{fontSize:12,color:"#ffffff99"}}>{lightbox+1} / {photos.length}</Text></View>
            <Animated.View style={{width:width-32,transform:[{scale:scaleAnim}]}}>
              <Image source={{uri:photos[lightbox]?.uri}} style={{width:"100%",height:300,borderRadius:16}} resizeMode="cover"/>
              <View style={{marginTop:14,alignItems:"center"}}><Text style={{fontSize:16,fontWeight:"700",color:"#fff",marginBottom:4}}>{photos[lightbox]?.label}</Text>{photos[lightbox]?.featured&&<View style={{backgroundColor:C.gold,borderRadius:8,paddingHorizontal:12,paddingVertical:4}}><Text style={{fontSize:10,fontWeight:"800",color:C.bg}}>★ FEATURED WORK</Text></View>}</View>
            </Animated.View>
            <View style={{flexDirection:"row",gap:16,marginTop:28}}>
              <TouchableOpacity onPress={goPrev} style={{width:52,height:52,borderRadius:26,backgroundColor:"#ffffff18",borderWidth:1,borderColor:"#ffffff33",alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:22,color:"#fff"}}>‹</Text></TouchableOpacity>
              <TouchableOpacity onPress={goNext}  style={{width:52,height:52,borderRadius:26,backgroundColor:"#ffffff18",borderWidth:1,borderColor:"#ffffff33",alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:22,color:"#fff"}}>›</Text></TouchableOpacity>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{position:"absolute",bottom:40}} contentContainerStyle={{paddingHorizontal:20,gap:8}}>
              {photos.map((ph,i)=>(<TouchableOpacity key={ph.id} onPress={()=>setLightbox(i)}><Image source={{uri:ph.uri}} style={{width:52,height:52,borderRadius:10,borderWidth:2,borderColor:i===lightbox?C.gold:"transparent",opacity:i===lightbox?1:0.5}} resizeMode="cover"/></TouchableOpacity>))}
            </ScrollView>
          </Animated.View>
        </Modal>
      )}
    </View>
  );
}

function PhotogProfile({ p, onBook, onBack, onChat }) {
  const [tab, setTab] = useState("About");
  return(
    <View style={{flex:1}}>
      <View style={{backgroundColor:C.card,padding:20,paddingTop:20}}>
        <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
          <TouchableOpacity onPress={onBack} style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:10,paddingHorizontal:14,paddingVertical:7}}><Text style={{color:C.text,fontSize:12}}>← Back</Text></TouchableOpacity>
          <TouchableOpacity style={{width:34,height:34,borderRadius:10,backgroundColor:C.card,borderWidth:1,borderColor:C.border,alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:16}}>♡</Text></TouchableOpacity>
        </View>
        <View style={{flexDirection:"row",gap:16,alignItems:"flex-end",marginBottom:20}}>
          <View>
            <Avatar initials={p.img} color={p.color} size={72}/>
            {p.avail&&<View style={{position:"absolute",bottom:2,right:2,width:14,height:14,borderRadius:7,backgroundColor:C.green,borderWidth:2,borderColor:C.bg}}/>}
          </View>
          <View>
            <Text style={{fontSize:22,fontWeight:"400",color:C.text}}>{p.name}</Text>
            <Text style={{fontSize:12,color:C.sub,marginTop:3}}>{p.role}</Text>
            <View style={{flexDirection:"row",alignItems:"center",gap:6,marginTop:6}}>
              <Stars rating={p.rating}/><Text style={{fontSize:13,color:C.gold,fontWeight:"700"}}>{p.rating}</Text><Text style={{fontSize:11,color:C.dim}}>· {p.reviews} reviews</Text>
            </View>
            {p.predictedRating && (
              <View style={{ marginTop:6 }}>
                <AIBadge score={typeof p.predictedRating === "number" ? p.predictedRating.toFixed(2) : p.predictedRating} isPersonalized={p.isPersonalized} />
              </View>
            )}
          </View>
        </View>
        <View style={{flexDirection:"row",gap:10,marginBottom:20}}>
          {[{label:"Bookings",val:p.bookings},{label:"Rating",val:p.rating},{label:"Reviews",val:p.reviews}].map(s=>(
            <View key={s.label} style={{flex:1,backgroundColor:C.bg+"BB",borderWidth:1,borderColor:C.border,borderRadius:12,padding:12,alignItems:"center"}}>
              <Text style={{fontSize:18,fontWeight:"800",color:C.text}}>{s.val}</Text>
              <Text style={{fontSize:10,color:C.sub,marginTop:3}}>{s.label}</Text>
            </View>
          ))}
        </View>
        <View style={{flexDirection:"row",borderBottomWidth:1,borderBottomColor:C.border}}>
          {["About","Portfolio","Reviews"].map(t=>(
            <TouchableOpacity key={t} onPress={()=>setTab(t)} style={{flex:1,alignItems:"center",paddingVertical:11,borderBottomWidth:2,borderBottomColor:tab===t?C.gold:"transparent"}}>
              <Text style={{fontSize:12,fontWeight:"600",color:tab===t?C.gold:C.sub}}>{t}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      <ScrollView style={{flex:1}} contentContainerStyle={{padding:20,paddingBottom:100}}>
        {tab==="About"&&(
          <View>
            <Text style={{fontSize:13,color:C.sub,lineHeight:22,marginBottom:20}}>{p.bio}</Text>
            <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.gold+"33",borderRadius:14,padding:18,marginBottom:16}}>
              <Text style={{fontSize:11,color:C.sub,marginBottom:4}}>STARTING FROM</Text>
              <Text style={{fontSize:28,fontWeight:"800",color:C.gold}}>PKR {Math.round(p.price/8).toLocaleString()}<Text style={{fontSize:12,color:C.sub,fontWeight:"400"}}> / hr</Text></Text>
            </View>
          </View>
        )}
        {tab==="Portfolio"&&<PortfolioGrid photogId={p.id}/>}
        {tab==="Reviews"&&(
          <View style={{gap:12}}>
            {[{name:"Sarah K.",rating:5,text:"Absolutely stunning work! Captured our wedding perfectly.",date:"Apr 2025"},{name:"Ahmed R.",rating:5,text:"Very professional and talented. Delivered on time.",date:"Mar 2025"},{name:"Nadia M.",rating:4.5,text:"Great experience overall. Photos came out beautifully.",date:"Feb 2025"}].map((r,i)=>(
              <View key={i} style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:16}}>
                <View style={{flexDirection:"row",justifyContent:"space-between",marginBottom:8}}>
                  <View style={{flexDirection:"row",alignItems:"center",gap:10}}>
                    <View style={{width:32,height:32,borderRadius:16,backgroundColor:C.gold+"33",alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:12,fontWeight:"700",color:C.gold}}>{r.name[0]}</Text></View>
                    <View><Text style={{fontSize:13,fontWeight:"600",color:C.text}}>{r.name}</Text><Text style={{fontSize:10,color:C.dim}}>{r.date}</Text></View>
                  </View>
                  <Stars rating={r.rating}/>
                </View>
                <Text style={{fontSize:12,color:C.sub,lineHeight:20}}>{r.text}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
      <View style={{padding:16,paddingBottom:20,backgroundColor:C.bg,gap:10}}>
        <View style={{flexDirection:"row",gap:10}}>
          <TouchableOpacity onPress={()=>onChat&&onChat(p)}
            style={{flex:1,paddingVertical:13,borderRadius:14,backgroundColor:C.card,borderWidth:1,borderColor:C.blue+"55",alignItems:"center",flexDirection:"row",justifyContent:"center",gap:8}}>
            <Text style={{fontSize:14}}>💬</Text>
            <Text style={{fontSize:13,fontWeight:"700",color:C.blue}}>Chat</Text>
            <View style={{backgroundColor:C.green,width:7,height:7,borderRadius:4}}/>
          </TouchableOpacity>
          <TouchableOpacity onPress={()=>onBook(p)}
            style={{flex:2,paddingVertical:13,borderRadius:14,backgroundColor:C.gold,alignItems:"center"}}>
            <Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>Book Now · PKR {Math.round(p.price/8).toLocaleString()} / hr</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

function BookingScreen({ p, onBack, onDone, currentUser }) {
  const [step,setStep]=useState(1);const[date,setDate]=useState("");const[type,setType]=useState("Wedding");const[hours,setHours]=useState(6);const[note,setNote]=useState("");const[dateError,setDateError]=useState("");const[conflictMsg,setConflictMsg]=useState("");const[toast,setToast]=useState(null);const[confirmedBooking,setConfirmedBooking]=useState(null);const[showCalendar,setShowCalendar]=useState(false);
  const bookedDates=BOOKINGS_STORE.getBookedDates(p.id);
  const total=Math.round((p.price/8)*hours);
  const shootTypes=["Wedding","Portrait","Fashion","Event","Corporate","Travel","Newborn","Family"];
  const validateDate=(val)=>{setDate(val);setDateError("");setConflictMsg("");if(!val)return;const d=new Date(val);const today=new Date();today.setHours(0,0,0,0);if(d<today){setDateError("Date cannot be in the past");return;}if(BOOKINGS_STORE.isPhotographerBooked(p.id,val)){setConflictMsg(`${p.name} is already booked on ${val}.`);}};
  const handleCalendarSelect=(ds)=>{setDate(ds);setDateError("");setConflictMsg("");if(BOOKINGS_STORE.isPhotographerBooked(p.id,ds)){setConflictMsg(`${p.name} is already booked on ${ds}.`);}};
  const proceedToConfirm=()=>{if(!date){setDateError("Please select a date");return;}if(dateError||conflictMsg)return;setStep(2);};
  const confirmBooking=async()=>{
    const apiResult = await API.createBooking({ photographer_id: p.apiId, user_id: currentUser.id, date, shoot_type: type, hours, amount: total }, currentUser.token);
    if (apiResult.success) {
      setConfirmedBooking({ ...apiResult.data, photog: p.name, date, type, hours, amount: total });
      return;
    }
    const result=BOOKINGS_STORE.addBooking({userId:currentUser.id,photogId:p.id,photog:p.name,date,type,status:"confirmed",amount:total,color:p.color,hours});
    if(result.success){setConfirmedBooking(result.booking);}
    else{setToast({message:result.error,type:"error"});setStep(1);setConflictMsg(result.error);}
  };
  if(confirmedBooking) return <BookingConfirmedAnimation booking={confirmedBooking} onDone={()=>{onDone();}}/>;
  return(
    <ScrollView style={{flex:1}}>
      {toast&&<Toast message={toast.message} type={toast.type} onDone={()=>setToast(null)}/>}
      <CalendarPicker selectedDate={date} onSelectDate={handleCalendarSelect} bookedDates={bookedDates} visible={showCalendar} onClose={()=>setShowCalendar(false)}/>
      <View style={{padding:20,paddingTop:20,flexDirection:"row",alignItems:"center",gap:14}}>
        <TouchableOpacity onPress={onBack} style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:10,paddingHorizontal:14,paddingVertical:7}}><Text style={{color:C.text,fontSize:12}}>← Back</Text></TouchableOpacity>
        <Text style={{fontSize:18,fontWeight:"400",color:C.text}}>Book <Text style={{color:C.gold,fontStyle:"italic"}}>{p.name}</Text></Text>
      </View>
      <View style={{flexDirection:"row",marginHorizontal:20,marginBottom:24,gap:8}}>
        {[{n:1,label:"Details"},{n:2,label:"Confirm"}].map(s=>(
          <View key={s.n} style={{flex:1,alignItems:"center",gap:6}}>
            <View style={{width:28,height:28,borderRadius:14,backgroundColor:step>=s.n?C.gold:C.card,borderWidth:2,borderColor:step>=s.n?C.gold:C.border,alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:12,fontWeight:"700",color:step>=s.n?C.bg:C.dim}}>{s.n}</Text></View>
            <Text style={{fontSize:10,color:step>=s.n?C.gold:C.dim}}>{s.label}</Text>
          </View>
        ))}
      </View>
      <View style={{paddingHorizontal:20}}>
        {step===1&&(
          <View style={{gap:14}}>
            <View>
              <Text style={{fontSize:11,color:C.sub,marginBottom:8,letterSpacing:0.5}}>SHOOT DATE *</Text>
              <TouchableOpacity onPress={()=>setShowCalendar(true)} style={{backgroundColor:C.card,borderWidth:1.5,borderColor:conflictMsg?C.red+"88":date?C.gold+"66":C.borderMid,borderRadius:14,padding:14,flexDirection:"row",alignItems:"center",gap:12,marginBottom:8}}>
                <View style={{width:40,height:40,borderRadius:12,backgroundColor:date?C.gold+"22":C.surface,borderWidth:1,borderColor:date?C.gold+"44":C.border,alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:20}}>📅</Text></View>
                <View style={{flex:1}}><Text style={{fontSize:12,color:C.dim,marginBottom:2}}>Tap to open calendar</Text><Text style={{fontSize:14,fontWeight:"700",color:date?C.text:C.dim}}>{date||"Select a date"}</Text></View>
                <View style={{backgroundColor:date?C.gold:C.surface,borderRadius:8,paddingHorizontal:10,paddingVertical:5,borderWidth:1,borderColor:date?C.gold:C.border}}><Text style={{fontSize:10,fontWeight:"700",color:date?C.bg:C.sub}}>OPEN</Text></View>
              </TouchableOpacity>
              <View style={{backgroundColor:C.surface,borderWidth:1,borderColor:C.border,borderRadius:12,padding:12,flexDirection:"row",alignItems:"center",gap:8}}>
                <Text style={{fontSize:11,color:C.dim}}>or type:</Text>
                <TextInput value={date} onChangeText={validateDate} placeholder="YYYY-MM-DD" placeholderTextColor={C.dim} style={{flex:1,color:C.text,fontSize:13}}/>
              </View>
              {dateError?<Text style={{fontSize:11,color:C.red,marginTop:6}}>⚠  {dateError}</Text>:null}
              {conflictMsg?<View style={{backgroundColor:C.redDim,borderWidth:1,borderColor:C.red+"44",borderRadius:12,padding:14,marginTop:8}}><Text style={{fontSize:12,color:C.red,fontWeight:"700",marginBottom:3}}>📅 Date Not Available</Text><Text style={{fontSize:11,color:C.sub,lineHeight:18}}>{conflictMsg}</Text></View>:date&&!dateError?<View style={{flexDirection:"row",alignItems:"center",gap:6,marginTop:6}}><Text style={{fontSize:11,color:C.green}}>✓  {date} is available</Text></View>:null}
              {bookedDates.length>0&&<View style={{backgroundColor:C.amberDim,borderWidth:1,borderColor:C.amber+"33",borderRadius:12,padding:12,marginTop:8}}><Text style={{fontSize:11,color:C.amber,fontWeight:"600",marginBottom:4}}>⚠ Already booked dates:</Text><Text style={{fontSize:11,color:C.sub}}>{bookedDates.join("  ·  ")}</Text></View>}
            </View>
            <View>
              <Text style={{fontSize:11,color:C.sub,marginBottom:7,letterSpacing:0.5}}>SHOOT TYPE</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                {shootTypes.map(t=><TouchableOpacity key={t} onPress={()=>setType(t)} style={{paddingHorizontal:14,paddingVertical:8,borderRadius:10,marginRight:8,backgroundColor:type===t?C.gold:C.card,borderWidth:1,borderColor:type===t?C.gold:C.border}}><Text style={{fontSize:12,color:type===t?C.bg:C.sub,fontWeight:"600"}}>{t}</Text></TouchableOpacity>)}
              </ScrollView>
            </View>
            <View>
              <Text style={{fontSize:11,color:C.sub,marginBottom:7,letterSpacing:0.5}}>DURATION: <Text style={{color:C.gold}}>{hours} hours</Text></Text>
              <View style={{flexDirection:"row",gap:8,flexWrap:"wrap"}}>
                {[2,3,4,5,6,8,10,12].map(h=><TouchableOpacity key={h} onPress={()=>setHours(h)} style={{paddingHorizontal:14,paddingVertical:8,borderRadius:10,backgroundColor:hours===h?C.gold:C.card,borderWidth:1,borderColor:hours===h?C.gold:C.border}}><Text style={{fontSize:12,color:hours===h?C.bg:C.sub,fontWeight:"600"}}>{h}h</Text></TouchableOpacity>)}
              </View>
            </View>
            <View>
              <Text style={{fontSize:11,color:C.sub,marginBottom:7,letterSpacing:0.5}}>SPECIAL NOTES (OPTIONAL)</Text>
              <TextInput value={note} onChangeText={setNote} multiline numberOfLines={3} placeholder="Any specific requirements..." placeholderTextColor={C.dim} style={{backgroundColor:C.card,borderWidth:1,borderColor:C.borderMid,borderRadius:12,padding:13,color:C.text,fontSize:13,height:80,textAlignVertical:"top"}}/>
            </View>
            <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:12,padding:14}}>
              <View style={{flexDirection:"row",justifyContent:"space-between",marginBottom:6}}><Text style={{fontSize:12,color:C.sub}}>PKR {(p.price/8).toLocaleString()} × {hours} hrs</Text><Text style={{fontSize:12,color:C.text,fontWeight:"600"}}>PKR {total.toLocaleString()}</Text></View>
              <View style={{flexDirection:"row",justifyContent:"space-between"}}><Text style={{fontSize:13,fontWeight:"700",color:C.text}}>Estimated Total</Text><Text style={{fontSize:13,fontWeight:"800",color:C.gold}}>PKR {total.toLocaleString()}</Text></View>
            </View>
            <TouchableOpacity onPress={proceedToConfirm} disabled={!!conflictMsg||!!dateError||!date} style={{paddingVertical:14,borderRadius:14,backgroundColor:(conflictMsg||dateError||!date)?C.card:C.gold,borderWidth:1,borderColor:(conflictMsg||dateError||!date)?C.border:C.gold,alignItems:"center"}}>
              <Text style={{fontSize:14,fontWeight:"800",color:(conflictMsg||dateError||!date)?C.dim:C.bg}}>Continue →</Text>
            </TouchableOpacity>
          </View>
        )}
        {step===2&&(
          <View>
            <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.gold+"33",borderRadius:14,padding:18,marginBottom:20}}>
              <Text style={{fontSize:14,fontWeight:"700",color:C.text,marginBottom:14}}>Booking Summary</Text>
              {[{label:"Photographer",val:p.name},{label:"Date",val:date},{label:"Type",val:type},{label:"Duration",val:hours+" hours"},{label:"Location",val:p.city},{label:"Payment",val:"Offline (Cash/Bank)"}].map(r=>(
                <View key={r.label} style={{flexDirection:"row",justifyContent:"space-between",paddingVertical:9,borderBottomWidth:1,borderBottomColor:C.border}}><Text style={{fontSize:12,color:C.sub}}>{r.label}</Text><Text style={{fontSize:12,fontWeight:"600",color:C.text}}>{r.val}</Text></View>
              ))}
              <View style={{flexDirection:"row",justifyContent:"space-between",paddingTop:12}}><Text style={{fontSize:15,fontWeight:"700",color:C.text}}>Total</Text><Text style={{fontSize:18,fontWeight:"800",color:C.gold}}>PKR {total.toLocaleString()}</Text></View>
            </View>
            <View style={{backgroundColor:C.greenDim,borderWidth:1.5,borderColor:C.green+"44",borderRadius:14,padding:16,marginBottom:14}}>
              <View style={{flexDirection:"row",gap:10,alignItems:"flex-start"}}>
                <Text style={{fontSize:18}}>🔒</Text>
                <View style={{flex:1}}>
                  <Text style={{fontSize:13,color:C.green,fontWeight:"800",marginBottom:4}}>Anti-Overbooking Guarantee</Text>
                  <Text style={{fontSize:11,color:C.sub,lineHeight:18}}>Once confirmed, this date is <Text style={{color:C.green}}>exclusively locked</Text> for you on {date}.</Text>
                </View>
              </View>
            </View>
            <View style={{backgroundColor:C.amberDim,borderWidth:1,borderColor:C.amber+"44",borderRadius:12,padding:14,marginBottom:20}}>
              <Text style={{fontSize:12,color:C.amber,fontWeight:"600",marginBottom:4}}>⚠ Offline Payment</Text>
              <Text style={{fontSize:11,color:C.sub}}>Payment collected directly from photographer upon confirmation.</Text>
            </View>
            <View style={{flexDirection:"row",gap:10}}>
              <TouchableOpacity onPress={()=>setStep(1)} style={{flex:1,paddingVertical:13,borderRadius:14,backgroundColor:C.card,borderWidth:1,borderColor:C.border,alignItems:"center"}}><Text style={{fontSize:13,fontWeight:"600",color:C.sub}}>← Edit</Text></TouchableOpacity>
              <TouchableOpacity onPress={confirmBooking} style={{flex:2,paddingVertical:13,borderRadius:14,backgroundColor:C.gold,alignItems:"center"}}><Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>Confirm Booking ✓</Text></TouchableOpacity>
            </View>
          </View>
        )}
      </View>
      <View style={{height:30}}/>
    </ScrollView>
  );
}

function BookingsScreen({ onNavigate, currentUser }) {
  const [tab, setTab] = useState("All");
  const tabs = ["All","Confirmed","Pending","Completed"];
  const myBookings = BOOKINGS_STORE.getUserBookings(currentUser.id);
  const list = tab==="All" ? myBookings : myBookings.filter(b => b.status===tab.toLowerCase());
  const counts = { confirmed:myBookings.filter(b=>b.status==="confirmed").length, pending:myBookings.filter(b=>b.status==="pending").length, completed:myBookings.filter(b=>b.status==="completed").length };
  return(
    <ScrollView style={{flex:1}} showsVerticalScrollIndicator={false}>
      <View style={{padding:20,paddingTop:24}}>
        <Text style={{fontSize:26,fontWeight:"400",color:C.text,marginBottom:6}}>My <Text style={{color:C.gold,fontStyle:"italic"}}>Bookings</Text></Text>
        <Text style={{fontSize:12,color:C.sub}}>{myBookings.length} total bookings</Text>
      </View>
      <View style={{flexDirection:"row",gap:10,paddingHorizontal:20,marginBottom:20}}>
        {[{label:"Confirmed",val:counts.confirmed,color:C.green},{label:"Pending",val:counts.pending,color:C.amber},{label:"Done",val:counts.completed,color:C.blue}].map(s=>(
          <View key={s.label} style={{flex:1,backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:12,padding:12,alignItems:"center"}}><Text style={{fontSize:20,fontWeight:"800",color:s.color}}>{s.val}</Text><Text style={{fontSize:10,color:C.sub,marginTop:3}}>{s.label}</Text></View>
        ))}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom:16}} contentContainerStyle={{paddingHorizontal:20}}>
        {tabs.map(t=><TouchableOpacity key={t} onPress={()=>setTab(t)} style={{paddingHorizontal:14,paddingVertical:6,borderRadius:20,marginRight:6,backgroundColor:tab===t?C.gold:C.card,borderWidth:1,borderColor:tab===t?C.gold:C.border}}><Text style={{fontSize:11,fontWeight:"600",color:tab===t?C.bg:C.sub}}>{t}</Text></TouchableOpacity>)}
      </ScrollView>
      <View style={{paddingHorizontal:20,gap:12}}>
        {list.length===0?(
          <View style={{alignItems:"center",paddingVertical:40}}>
            <Text style={{fontSize:40,marginBottom:14}}>📷</Text>
            <Text style={{fontSize:15,color:C.text,fontWeight:"600",marginBottom:6}}>No bookings yet</Text>
            <Text style={{fontSize:12,color:C.sub,textAlign:"center"}}>Explore photographers and book your first shoot!</Text>
          </View>
        ):list.map(b=>(
          <View key={b.id} style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:16,padding:16,borderLeftWidth:3,borderLeftColor:b.color}}>
            <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
              <View><Text style={{fontSize:14,fontWeight:"700",color:C.text}}>{b.photog}</Text><Text style={{fontSize:11,color:C.sub,marginTop:2}}>{b.type}</Text></View>
              <StatusBadge status={b.status}/>
            </View>
            <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
              <Text style={{fontSize:12,color:C.sub}}>📅 {b.date}</Text>
              <Text style={{fontSize:15,fontWeight:"800",color:C.gold}}>PKR {b.amount.toLocaleString()}</Text>
            </View>
          </View>
        ))}
      </View>
      <View style={{height:20}}/>
    </ScrollView>
  );
}

function DashboardScreen({ currentUser }) {
  const { recommendations, recType, apiConnected } = useRecommendations(currentUser);
  const maxB=Math.max(...ANALYTICS.monthlyData.map(d=>d.bookings));
  return(
    <ScrollView style={{flex:1}} showsVerticalScrollIndicator={false}>
      <View style={{padding:20,paddingTop:24}}>
        <Text style={{fontSize:11,color:C.gold,letterSpacing:1.8,textTransform:"uppercase",marginBottom:6}}>Analytics & Insights</Text>
        <Text style={{fontSize:26,fontWeight:"400",color:C.text}}>Performance <Text style={{color:C.gold,fontStyle:"italic"}}>Dashboard</Text></Text>
      </View>
      <View style={{flexDirection:"row",flexWrap:"wrap",gap:10,paddingHorizontal:20,marginBottom:20}}>
        {[{label:"Total Bookings",val:"186",icon:"📅",color:C.gold},{label:"Total Revenue",val:"248k PKR",icon:"💰",color:C.green},{label:"Avg Rating",val:"4.78 ★",icon:"⭐",color:C.amber},{label:"Profile Views",val:"3.2k",icon:"👁",color:C.blue}].map(k=>(
          <View key={k.label} style={{width:"47%",backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:16}}>
            <Text style={{fontSize:20,marginBottom:8}}>{k.icon}</Text>
            <Text style={{fontSize:22,fontWeight:"800",color:k.color}}>{k.val}</Text>
            <Text style={{fontSize:10,color:C.sub,marginTop:5}}>{k.label}</Text>
          </View>
        ))}
      </View>
      <View style={{marginHorizontal:20,backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:16,padding:18,marginBottom:14}}>
        <Text style={{fontSize:13,fontWeight:"700",color:C.text,marginBottom:16}}>Monthly Bookings</Text>
        <View style={{flexDirection:"row",alignItems:"flex-end",height:80,marginBottom:8}}>
          {ANALYTICS.monthlyData.map((d,i)=>(
            <View key={i} style={{flex:1,alignItems:"center",gap:4,justifyContent:"flex-end"}}>
              <Text style={{fontSize:9,color:C.sub}}>{d.bookings}</Text>
              <View style={{width:"70%",borderRadius:4,height:Math.max(4,(d.bookings/maxB)*56),backgroundColor:i===ANALYTICS.monthlyData.length-1?C.gold:C.gold+"55"}}/>
              <Text style={{fontSize:9,color:C.dim}}>{d.month}</Text>
            </View>
          ))}
        </View>
      </View>
      <View style={{marginHorizontal:20,backgroundColor:C.blueDim,borderWidth:1,borderColor:C.blue+"44",borderRadius:16,padding:18,marginBottom:20}}>
        <View style={{flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <Text style={{fontSize:13,fontWeight:"700",color:C.text}}>🤖 AI Model Insights</Text>
          <View style={{flexDirection:"row",alignItems:"center",gap:5}}>
            <View style={{width:6,height:6,borderRadius:3,backgroundColor:apiConnected?C.green:C.amber}}/>
            <Text style={{fontSize:9,color:apiConnected?C.green:C.amber}}>{apiConnected?"Django API":"Local Model"}</Text>
          </View>
        </View>
        <View style={{backgroundColor:C.bg+"44",borderRadius:12,padding:12,marginBottom:12}}>
          <Text style={{fontSize:11,color:C.sub,marginBottom:6}}>Top AI-Recommended This Week</Text>
          {recommendations.slice(0,3).map((p,i)=>(
            <View key={p.id} style={{flexDirection:"row",alignItems:"center",gap:10,paddingVertical:6,borderBottomWidth:i<2?1:0,borderBottomColor:C.border+"88"}}>
              <Text style={{fontSize:12,color:C.dim,width:16}}>#{i+1}</Text>
              <Avatar initials={p.img} color={p.color} size={28}/>
              <Text style={{flex:1,fontSize:12,color:C.text}}>{p.name}</Text>
              <Text style={{fontSize:11,fontWeight:"700",color:C.gold}}>{p.predictedRating}★</Text>
            </View>
          ))}
        </View>
        {["Peak demand expected in July — consider raising rates by 10–15%.","Wedding bookings up 34%. Expand portfolio with more ceremony shots.","3 profile views converted to bookings — 12% conversion rate."].map((tip,i)=>(
          <View key={i} style={{flexDirection:"row",gap:10,marginBottom:10}}>
            <View style={{width:6,height:6,borderRadius:3,backgroundColor:C.blue,marginTop:7,flexShrink:0}}/>
            <Text style={{fontSize:12,color:C.sub,lineHeight:20,flex:1}}>{tip}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

function EditProfileModal({ visible, onClose, currentUser, onSave }) {
  const [name,  setName]  = useState(currentUser?.name  || "");
  const [phone, setPhone] = useState(currentUser?.phone || "");
  const [city,  setCity]  = useState(currentUser?.city  || "");
  const [saved, setSaved] = useState(false);
  const CITIES = ["Islamabad","Rawalpindi","Lahore","Karachi","Peshawar","Quetta","Multan","Faisalabad"];

  const handleSave = () => {
    if (!name.trim()) return;
    onSave({ name: name.trim(), phone: phone.trim(), city });
    setSaved(true);
    setTimeout(() => { setSaved(false); onClose(); }, 1200);
  };

  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==="ios"?"padding":undefined}>
        <View style={{flex:1,backgroundColor:"#000000BB"}}>
          <TouchableOpacity style={{flex:1}} activeOpacity={1} onPress={onClose}/>
          <View style={{backgroundColor:C.surface,borderTopLeftRadius:24,borderTopRightRadius:24,borderWidth:1,borderColor:C.border,padding:24}}>
            <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",marginBottom:20}}>
              <Text style={{fontSize:18,fontWeight:"800",color:C.text}}>Edit Profile</Text>
              <TouchableOpacity onPress={onClose} style={{width:32,height:32,borderRadius:16,backgroundColor:C.card,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.border}}>
                <Text style={{color:C.text}}>✕</Text>
              </TouchableOpacity>
            </View>
            <Text style={{fontSize:11,color:C.sub,marginBottom:6,letterSpacing:0.5}}>FULL NAME</Text>
            <TextInput value={name} onChangeText={setName} placeholder="Your full name"
              placeholderTextColor={C.dim}
              style={{backgroundColor:C.card,borderWidth:1.5,borderColor:C.borderMid,borderRadius:12,padding:13,color:C.text,fontSize:13,marginBottom:14}}/>
            <Text style={{fontSize:11,color:C.sub,marginBottom:6,letterSpacing:0.5}}>PHONE</Text>
            <TextInput value={phone} onChangeText={setPhone} placeholder="03001234567"
              placeholderTextColor={C.dim} keyboardType="phone-pad"
              style={{backgroundColor:C.card,borderWidth:1.5,borderColor:C.borderMid,borderRadius:12,padding:13,color:C.text,fontSize:13,marginBottom:14}}/>
            <Text style={{fontSize:11,color:C.sub,marginBottom:8,letterSpacing:0.5}}>CITY</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom:20}}>
              {CITIES.map(c=>(
                <TouchableOpacity key={c} onPress={()=>setCity(c)}
                  style={{paddingHorizontal:14,paddingVertical:8,borderRadius:20,marginRight:8,backgroundColor:city===c?C.gold:C.card,borderWidth:1,borderColor:city===c?C.gold:C.border}}>
                  <Text style={{fontSize:12,fontWeight:"600",color:city===c?C.bg:C.sub}}>{c}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TouchableOpacity onPress={handleSave}
              style={{paddingVertical:14,borderRadius:13,backgroundColor:saved?C.green:C.gold,alignItems:"center"}}>
              <Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>{saved?"✓ Saved!":"Save Changes"}</Text>
            </TouchableOpacity>
            <View style={{height:Platform.OS==="ios"?20:8}}/>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function WishlistModal({ visible, onClose, onViewPhotog }) {
  const wishlist = PHOTOGRAPHERS.filter(p => [1,3,5].includes(p.id));
  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <View style={{flex:1,backgroundColor:"#000000BB"}}>
        <TouchableOpacity style={{flex:1}} activeOpacity={1} onPress={onClose}/>
        <View style={{backgroundColor:C.surface,borderTopLeftRadius:24,borderTopRightRadius:24,borderWidth:1,borderColor:C.border,maxHeight:"75%"}}>
          <View style={{padding:20,flexDirection:"row",justifyContent:"space-between",alignItems:"center",borderBottomWidth:1,borderBottomColor:C.border}}>
            <View>
              <Text style={{fontSize:18,fontWeight:"800",color:C.text}}>My Wishlist</Text>
              <Text style={{fontSize:11,color:C.sub,marginTop:2}}>{wishlist.length} saved photographers</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{width:32,height:32,borderRadius:16,backgroundColor:C.card,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.border}}>
              <Text style={{color:C.text}}>✕</Text>
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={{padding:16,gap:10}}>
            {wishlist.length===0 ? (
              <View style={{alignItems:"center",paddingVertical:40}}>
                <Text style={{fontSize:32,marginBottom:12}}>❤</Text>
                <Text style={{fontSize:14,color:C.sub}}>No saved photographers yet</Text>
              </View>
            ) : wishlist.map(p=>(
              <TouchableOpacity key={p.id} onPress={()=>{onClose(); onViewPhotog&&onViewPhotog(p);}}
                style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:14,flexDirection:"row",alignItems:"center",gap:12}}>
                <View style={{width:46,height:46,borderRadius:23,backgroundColor:p.color+"99",alignItems:"center",justifyContent:"center",borderWidth:1.5,borderColor:p.color+"88"}}>
                  <Text style={{fontSize:13,fontWeight:"700",color:"#fff"}}>{p.img}</Text>
                </View>
                <View style={{flex:1}}>
                  <Text style={{fontSize:14,fontWeight:"700",color:C.text}}>{p.name}</Text>
                  <Text style={{fontSize:11,color:C.sub,marginTop:1}}>{p.role} · {p.city}</Text>
                </View>
                <View style={{alignItems:"flex-end"}}>
                  <Text style={{fontSize:13,fontWeight:"800",color:C.gold}}>PKR {(p.price/1000).toFixed(0)}k</Text>
                  <Text style={{fontSize:10,color:C.red,marginTop:3}}>❤ Saved</Text>
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function PaymentHistoryModal({ visible, onClose, currentUser }) {
  const bookings = BOOKINGS_STORE.getUserBookings(currentUser.id);
  const total    = bookings.reduce((s, b) => s + (b.amount || 0), 0);
  const STATUS_COLOR = { confirmed:C.green, completed:C.blue, pending:C.amber, cancelled:C.red };

  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <View style={{flex:1,backgroundColor:"#000000BB"}}>
        <TouchableOpacity style={{flex:1}} activeOpacity={1} onPress={onClose}/>
        <View style={{backgroundColor:C.surface,borderTopLeftRadius:24,borderTopRightRadius:24,borderWidth:1,borderColor:C.border,maxHeight:"80%"}}>
          <View style={{padding:20,flexDirection:"row",justifyContent:"space-between",alignItems:"center",borderBottomWidth:1,borderBottomColor:C.border}}>
            <View>
              <Text style={{fontSize:18,fontWeight:"800",color:C.text}}>Payment History</Text>
              <Text style={{fontSize:11,color:C.sub,marginTop:2}}>{bookings.length} transactions</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{width:32,height:32,borderRadius:16,backgroundColor:C.card,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.border}}>
              <Text style={{color:C.text}}>✕</Text>
            </TouchableOpacity>
          </View>
          <View style={{margin:16,backgroundColor:C.gold+"18",borderWidth:1,borderColor:C.gold+"33",borderRadius:14,padding:16,flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
            <View>
              <Text style={{fontSize:11,color:C.sub}}>Total Spent</Text>
              <Text style={{fontSize:22,fontWeight:"800",color:C.gold,marginTop:2}}>PKR {total.toLocaleString()}</Text>
            </View>
            <Text style={{fontSize:32}}>💳</Text>
          </View>
          <ScrollView contentContainerStyle={{paddingHorizontal:16,paddingBottom:20,gap:10}}>
            {bookings.length===0 ? (
              <View style={{alignItems:"center",paddingVertical:40}}>
                <Text style={{fontSize:32,marginBottom:12}}>💳</Text>
                <Text style={{fontSize:14,color:C.sub}}>No payment history yet</Text>
              </View>
            ) : bookings.map(b=>(
              <View key={b.id} style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:14}}>
                <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
                  <View style={{flex:1}}>
                    <Text style={{fontSize:13,fontWeight:"700",color:C.text}}>{b.photog}</Text>
                    <Text style={{fontSize:11,color:C.sub,marginTop:2}}>{b.type} · {b.hours}hrs</Text>
                  </View>
                  <View style={{paddingHorizontal:8,paddingVertical:3,borderRadius:6,backgroundColor:(STATUS_COLOR[b.status]||C.border)+"22",borderWidth:1,borderColor:(STATUS_COLOR[b.status]||C.border)+"44"}}>
                    <Text style={{fontSize:10,fontWeight:"700",color:STATUS_COLOR[b.status]||C.text,textTransform:"uppercase"}}>{b.status}</Text>
                  </View>
                </View>
                <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",paddingTop:8,borderTopWidth:1,borderTopColor:C.border}}>
                  <Text style={{fontSize:11,color:C.sub}}>📅 {b.date}</Text>
                  <Text style={{fontSize:14,fontWeight:"800",color:C.gold}}>PKR {b.amount?.toLocaleString()}</Text>
                </View>
                <View style={{marginTop:6,backgroundColor:C.amberDim,borderRadius:8,padding:8}}>
                  <Text style={{fontSize:10,color:C.amber}}>💳 Offline Payment · Cash / Bank Transfer</Text>
                </View>
              </View>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function PrivacySecurityModal({ visible, onClose, currentUser }) {
  const [oldPass,  setOldPass]  = useState("");
  const [newPass,  setNewPass]  = useState("");
  const [confirm,  setConfirm]  = useState("");
  const [msg,      setMsg]      = useState(null);
  const [twoFA,    setTwoFA]    = useState(false);
  const [emailNot, setEmailNot] = useState(true);
  const [smsNot,   setSmsNot]   = useState(false);

  const changePassword = () => {
    if (!oldPass || !newPass || !confirm) { setMsg({text:"All fields required",type:"error"}); return; }
    if (newPass.length < 6) { setMsg({text:"Min 6 characters",type:"error"}); return; }
    if (newPass !== confirm) { setMsg({text:"Passwords don't match",type:"error"}); return; }
    setMsg({text:"✓ Password changed successfully!",type:"success"});
    setOldPass(""); setNewPass(""); setConfirm("");
    setTimeout(()=>setMsg(null), 3000);
  };

  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==="ios"?"padding":undefined}>
        <View style={{flex:1,backgroundColor:"#000000BB"}}>
          <TouchableOpacity style={{flex:1}} activeOpacity={1} onPress={onClose}/>
          <View style={{backgroundColor:C.surface,borderTopLeftRadius:24,borderTopRightRadius:24,borderWidth:1,borderColor:C.border,maxHeight:"85%"}}>
            <View style={{padding:20,flexDirection:"row",justifyContent:"space-between",alignItems:"center",borderBottomWidth:1,borderBottomColor:C.border}}>
              <Text style={{fontSize:18,fontWeight:"800",color:C.text}}>Privacy & Security</Text>
              <TouchableOpacity onPress={onClose} style={{width:32,height:32,borderRadius:16,backgroundColor:C.card,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.border}}>
                <Text style={{color:C.text}}>✕</Text>
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{padding:20,gap:16}}>
              <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:16}}>
                <Text style={{fontSize:14,fontWeight:"700",color:C.text,marginBottom:14}}>🔒 Change Password</Text>
                {msg && (
                  <View style={{backgroundColor:msg.type==="success"?C.greenDim:C.redDim,borderRadius:8,padding:10,marginBottom:12,borderWidth:1,borderColor:msg.type==="success"?C.green+"44":C.red+"44"}}>
                    <Text style={{fontSize:12,color:msg.type==="success"?C.green:C.red}}>{msg.text}</Text>
                  </View>
                )}
                {[
                  {label:"Current Password", val:oldPass, set:setOldPass},
                  {label:"New Password",     val:newPass, set:setNewPass},
                  {label:"Confirm New",      val:confirm, set:setConfirm},
                ].map(f=>(
                  <View key={f.label} style={{marginBottom:10}}>
                    <Text style={{fontSize:10,color:C.sub,marginBottom:4}}>{f.label.toUpperCase()}</Text>
                    <TextInput value={f.val} onChangeText={f.set} secureTextEntry
                      placeholder="••••••" placeholderTextColor={C.dim}
                      style={{backgroundColor:C.surface,borderWidth:1,borderColor:C.borderMid,borderRadius:10,padding:11,color:C.text,fontSize:13}}/>
                  </View>
                ))}
                <TouchableOpacity onPress={changePassword}
                  style={{paddingVertical:11,borderRadius:10,backgroundColor:C.gold,alignItems:"center",marginTop:4}}>
                  <Text style={{fontSize:13,fontWeight:"700",color:C.bg}}>Update Password</Text>
                </TouchableOpacity>
              </View>

              <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:16,gap:14}}>
                <Text style={{fontSize:14,fontWeight:"700",color:C.text,marginBottom:2}}>🛡️ Security Settings</Text>
                {[
                  {label:"Two-Factor Authentication",sub:"Extra security on login",val:twoFA,set:setTwoFA},
                  {label:"Email Notifications",      sub:"Booking alerts via email", val:emailNot,set:setEmailNot},
                  {label:"SMS Notifications",        sub:"Alerts via SMS",            val:smsNot,set:setSmsNot},
                ].map(s=>(
                  <View key={s.label} style={{flexDirection:"row",alignItems:"center",justifyContent:"space-between"}}>
                    <View style={{flex:1}}>
                      <Text style={{fontSize:13,fontWeight:"600",color:C.text}}>{s.label}</Text>
                      <Text style={{fontSize:11,color:C.sub,marginTop:2}}>{s.sub}</Text>
                    </View>
                    <TouchableOpacity onPress={()=>s.set(!s.val)}
                      style={{width:44,height:24,borderRadius:12,backgroundColor:s.val?C.gold:C.border,padding:2,justifyContent:"center"}}>
                      <View style={{width:20,height:20,borderRadius:10,backgroundColor:"#fff",alignSelf:s.val?"flex-end":"flex-start"}}/>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>

              <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:16}}>
                <Text style={{fontSize:14,fontWeight:"700",color:C.text,marginBottom:12}}>👤 Account Info</Text>
                {[
                  {label:"Email",  val:currentUser?.email},
                  {label:"Role",   val:currentUser?.role},
                  {label:"City",   val:currentUser?.city||"Not set"},
                  {label:"Phone",  val:currentUser?.phone||"Not set"},
                  {label:"Member Since",val:"2025"},
                ].map(r=>(
                  <View key={r.label} style={{flexDirection:"row",justifyContent:"space-between",paddingVertical:8,borderBottomWidth:1,borderBottomColor:C.border}}>
                    <Text style={{fontSize:12,color:C.sub}}>{r.label}</Text>
                    <Text style={{fontSize:12,fontWeight:"600",color:C.text}}>{r.val}</Text>
                  </View>
                ))}
              </View>
            </ScrollView>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function HelpSupportModal({ visible, onClose }) {
  const [activeQ, setActiveQ] = useState(null);
  const [msg,     setMsg]     = useState("");
  const [sent,    setSent]    = useState(false);

  const FAQS = [
    {q:"How do I book a photographer?", a:"Go to Explore, pick a photographer, tap their profile then 'Book Now'. Choose your date, shoot type and hours. Confirm to lock the slot."},
    {q:"Can I cancel a booking?",       a:"Yes. Go to My Bookings, select the booking and tap Cancel. Cancellations must be made 24 hours before the shoot date."},
    {q:"How does payment work?",        a:"SnapSphere uses offline payment. You pay the photographer directly via cash or bank transfer on the shoot day."},
    {q:"What is anti-overbooking?",     a:"Once you confirm a date, that slot is exclusively locked for you. No other client can book the same photographer on the same date."},
    {q:"How are photographers recommended?", a:"We use SVD Collaborative Filtering — an AI model trained on user ratings to predict which photographers you'll love."},
    {q:"How do I become a photographer?", a:"Register an account, choose 'Photographer' role. Your profile will appear in the marketplace after setup."},
  ];

  const sendMessage = () => {
    if (!msg.trim()) return;
    setSent(true);
    setMsg("");
    setTimeout(()=>setSent(false), 3000);
  };

  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==="ios"?"padding":undefined}>
        <View style={{flex:1,backgroundColor:"#000000BB"}}>
          <TouchableOpacity style={{flex:1}} activeOpacity={1} onPress={onClose}/>
          <View style={{backgroundColor:C.surface,borderTopLeftRadius:24,borderTopRightRadius:24,borderWidth:1,borderColor:C.border,maxHeight:"88%"}}>
            <View style={{padding:20,flexDirection:"row",justifyContent:"space-between",alignItems:"center",borderBottomWidth:1,borderBottomColor:C.border}}>
              <View>
                <Text style={{fontSize:18,fontWeight:"800",color:C.text}}>Help & Support</Text>
                <Text style={{fontSize:11,color:C.sub,marginTop:2}}>FAQs & contact us</Text>
              </View>
              <TouchableOpacity onPress={onClose} style={{width:32,height:32,borderRadius:16,backgroundColor:C.card,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.border}}>
                <Text style={{color:C.text}}>✕</Text>
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{padding:16,gap:12}} keyboardShouldPersistTaps="handled">
              <Text style={{fontSize:14,fontWeight:"700",color:C.text,marginBottom:4}}>❓ Frequently Asked Questions</Text>
              {FAQS.map((faq,i)=>(
                <TouchableOpacity key={i} onPress={()=>setActiveQ(activeQ===i?null:i)}
                  style={{backgroundColor:C.card,borderWidth:1,borderColor:activeQ===i?C.gold+"44":C.border,borderRadius:14,overflow:"hidden"}}>
                  <View style={{padding:14,flexDirection:"row",alignItems:"center",gap:10}}>
                    <View style={{width:24,height:24,borderRadius:12,backgroundColor:activeQ===i?C.gold:C.surface,alignItems:"center",justifyContent:"center",flexShrink:0}}>
                      <Text style={{fontSize:11,fontWeight:"800",color:activeQ===i?C.bg:C.sub}}>{activeQ===i?"−":"+"}</Text>
                    </View>
                    <Text style={{flex:1,fontSize:13,fontWeight:"600",color:activeQ===i?C.gold:C.text}}>{faq.q}</Text>
                  </View>
                  {activeQ===i && (
                    <View style={{paddingHorizontal:14,paddingBottom:14,paddingTop:2}}>
                      <Text style={{fontSize:12,color:C.sub,lineHeight:20}}>{faq.a}</Text>
                    </View>
                  )}
                </TouchableOpacity>
              ))}

              <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:16,marginTop:4}}>
                <Text style={{fontSize:14,fontWeight:"700",color:C.text,marginBottom:12}}>📩 Send us a Message</Text>
                {sent ? (
                  <View style={{backgroundColor:C.greenDim,borderRadius:10,padding:14,alignItems:"center",borderWidth:1,borderColor:C.green+"44"}}>
                    <Text style={{fontSize:20,marginBottom:6}}>✅</Text>
                    <Text style={{fontSize:13,color:C.green,fontWeight:"700"}}>Message Sent!</Text>
                    <Text style={{fontSize:11,color:C.sub,marginTop:4}}>We'll reply within 24 hours.</Text>
                  </View>
                ) : (
                  <>
                    <TextInput value={msg} onChangeText={setMsg}
                      placeholder="Describe your issue or question..." placeholderTextColor={C.dim}
                      multiline numberOfLines={4}
                      style={{backgroundColor:C.surface,borderWidth:1,borderColor:C.borderMid,borderRadius:12,padding:12,color:C.text,fontSize:13,height:100,textAlignVertical:"top",marginBottom:12}}/>
                    <TouchableOpacity onPress={sendMessage}
                      style={{paddingVertical:12,borderRadius:12,backgroundColor:C.gold,alignItems:"center"}}>
                      <Text style={{fontSize:13,fontWeight:"700",color:C.bg}}>Send Message 📩</Text>
                    </TouchableOpacity>
                  </>
                )}
              </View>

              <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:16}}>
                <Text style={{fontSize:13,fontWeight:"700",color:C.text,marginBottom:10}}>📞 Contact Info</Text>
                {[
                  {icon:"📧",label:"Email",val:"support@snapsphere.pk"},
                  {icon:"📱",label:"WhatsApp",val:"+92 300 1234567"},
                  {icon:"🕐",label:"Hours",val:"Mon–Sat, 9am–6pm PKT"},
                  {icon:"📍",label:"Office",val:"COMSATS University, Attock"},
                ].map(c=>(
                  <View key={c.label} style={{flexDirection:"row",alignItems:"center",gap:10,paddingVertical:7,borderBottomWidth:1,borderBottomColor:C.border}}>
                    <Text style={{fontSize:16}}>{c.icon}</Text>
                    <Text style={{fontSize:11,color:C.sub,width:70}}>{c.label}</Text>
                    <Text style={{fontSize:12,color:C.text,fontWeight:"600",flex:1}}>{c.val}</Text>
                  </View>
                ))}
              </View>
              <View style={{height:8}}/>
            </ScrollView>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function ProfileScreen({ onNavigate, currentUser, onLogout, onSwitchRole, onUpdateUser }) {
  const [showLogout,  setShowLogout]  = useState(false);
  const [showEdit,    setShowEdit]    = useState(false);
  const [showNotifs,  setShowNotifs]  = useState(false);
  const [showWish,    setShowWish]    = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [showHelp,    setShowHelp]    = useState(false);
  const [userData,    setUserData]    = useState(currentUser);
  const [toast,       setToast]       = useState(null);

  const myBookings = BOOKINGS_STORE.getUserBookings(currentUser.id);
  const initial    = userData?.name?.[0]?.toUpperCase() || "U";
  const isPhotog   = currentUser?.activeRole === "photographer";

  const handleSaveProfile = (updates) => {
    setUserData(prev => ({ ...prev, ...updates }));
    onUpdateUser && onUpdateUser(updates);
    setToast({ message:"✓ Profile updated successfully!", type:"success" });
  };

  const MENU_ITEMS = [
    { icon:"📝", title:"Edit Profile",      sub:"Update your info & preferences",  onPress:()=>setShowEdit(true),    col:C.gold  },
    { icon:"🔔", title:"Notifications",     sub:"Booking alerts & messages",        onPress:()=>setShowNotifs(true),  col:C.amber },
    { icon:"❤",  title:"My Wishlist",       sub:"Saved photographers",              onPress:()=>setShowWish(true),    col:C.red   },
    { icon:"💳", title:"Payment History",   sub:"View past transactions",           onPress:()=>setShowPayment(true), col:C.green },
    { icon:"📊", title:"Analytics",          sub:"View your performance stats",     onPress:()=>onNavigate("Dashboard"), col:C.blue  },
    { icon:"🔒", title:"Privacy & Security",sub:"Password & account settings",      onPress:()=>setShowPrivacy(true), col:C.blue  },
    { icon:"📞", title:"Help & Support",    sub:"FAQs, contact us",                 onPress:()=>setShowHelp(true),    col:C.sub   },
  ];

  return (
    <View style={{flex:1}}>
      {toast && <Toast message={toast.message} type={toast.type} onDone={()=>setToast(null)}/>}

      <EditProfileModal
        visible={showEdit} onClose={()=>setShowEdit(false)}
        currentUser={userData} onSave={handleSaveProfile}/>
      <NotificationsPanel
        userId={currentUser.id} visible={showNotifs} onClose={()=>setShowNotifs(false)}/>
      <WishlistModal
        visible={showWish} onClose={()=>setShowWish(false)} onViewPhotog={null}/>
      <PaymentHistoryModal
        visible={showPayment} onClose={()=>setShowPayment(false)} currentUser={currentUser}/>
      <PrivacySecurityModal
        visible={showPrivacy} onClose={()=>setShowPrivacy(false)} currentUser={userData}/>
      <HelpSupportModal
        visible={showHelp} onClose={()=>setShowHelp(false)}/>

      {showLogout && (
        <View style={{position:"absolute",top:0,left:0,right:0,bottom:0,backgroundColor:"#000000AA",zIndex:1000,alignItems:"center",justifyContent:"center",padding:32}}>
          <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:20,padding:28,width:"100%"}}>
            <View style={{width:54,height:54,borderRadius:27,backgroundColor:C.redDim,alignItems:"center",justifyContent:"center",marginBottom:16,alignSelf:"center"}}>
              <Text style={{fontSize:24}}>👋</Text>
            </View>
            <Text style={{fontSize:18,fontWeight:"800",color:C.text,textAlign:"center",marginBottom:8}}>Sign Out?</Text>
            <Text style={{fontSize:13,color:C.sub,textAlign:"center",lineHeight:20,marginBottom:24}}>You'll be returned to the login screen.</Text>
            <View style={{flexDirection:"row",gap:10}}>
              <TouchableOpacity onPress={()=>setShowLogout(false)} style={{flex:1,paddingVertical:13,borderRadius:12,backgroundColor:C.surface,borderWidth:1,borderColor:C.border,alignItems:"center"}}>
                <Text style={{fontSize:13,fontWeight:"600",color:C.sub}}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={onLogout} style={{flex:1,paddingVertical:13,borderRadius:12,backgroundColor:C.red,alignItems:"center"}}>
                <Text style={{fontSize:13,fontWeight:"700",color:"#fff"}}>Sign Out</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      <ScrollView style={{flex:1}} showsVerticalScrollIndicator={false}>
        <View style={{padding:20,paddingTop:24}}>
          <Text style={{fontSize:26,fontWeight:"400",color:C.text,marginBottom:20}}>
            My <Text style={{color:C.gold,fontStyle:"italic"}}>Profile</Text>
          </Text>

          <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.gold+"33",borderRadius:18,padding:20,marginBottom:20}}>
            <View style={{flexDirection:"row",gap:14,alignItems:"center",marginBottom:16}}>
              <TouchableOpacity onPress={()=>setShowEdit(true)} style={{position:"relative"}}>
                <View style={{width:64,height:64,borderRadius:32,backgroundColor:C.gold,alignItems:"center",justifyContent:"center"}}>
                  <Text style={{fontSize:24,fontWeight:"800",color:C.bg}}>{initial}</Text>
                </View>
                <View style={{position:"absolute",bottom:0,right:0,width:20,height:20,borderRadius:10,backgroundColor:C.gold,borderWidth:2,borderColor:C.card,alignItems:"center",justifyContent:"center"}}>
                  <Text style={{fontSize:10}}>✏️</Text>
                </View>
              </TouchableOpacity>
              <View style={{flex:1}}>
                <Text style={{fontSize:18,fontWeight:"700",color:C.text}}>{userData?.name}</Text>
                <Text style={{fontSize:12,color:C.sub,marginTop:2}}>{userData?.city||"Pakistan"}</Text>
                <Text style={{fontSize:11,color:C.dim,marginTop:1}}>{userData?.email}</Text>
                {userData?.phone ? <Text style={{fontSize:11,color:C.dim,marginTop:1}}>📱 {userData.phone}</Text> : null}
              </View>
              <TouchableOpacity onPress={()=>setShowEdit(true)}
                style={{backgroundColor:C.gold+"18",borderWidth:1,borderColor:C.gold+"44",borderRadius:10,paddingHorizontal:12,paddingVertical:6}}>
                <Text style={{fontSize:11,fontWeight:"700",color:C.gold}}>Edit</Text>
              </TouchableOpacity>
            </View>
            <View style={{paddingTop:14,borderTopWidth:1,borderTopColor:C.border}}>
              <Text style={{fontSize:11,color:C.sub,marginBottom:10,letterSpacing:0.5}}>CURRENT MODE</Text>
              <View style={{flexDirection:"row",alignItems:"center",justifyContent:"space-between"}}>
                <View style={{flex:1}}>
                  <Text style={{fontSize:14,fontWeight:"700",color:isPhotog?C.gold:C.blue}}>
                    {isPhotog?"📸 Photographer Mode":"🔍 Buyer / Client Mode"}
                  </Text>
                  <Text style={{fontSize:11,color:C.sub,marginTop:2}}>
                    {isPhotog?"Managing your portfolio & bookings":"Browsing & booking photographers"}
                  </Text>
                </View>
                <RoleSwitcher currentUser={currentUser} onSwitch={onSwitchRole}/>
              </View>
            </View>
          </View>

          <View style={{flexDirection:"row",gap:10,marginBottom:20}}>
            {[
              {label:"Bookings", val:myBookings.length,             col:C.gold,  onPress:()=>onNavigate("Bookings")},
              {label:"Wishlist", val:3,                             col:C.blue,  onPress:()=>setShowWish(true)},
              {label:"Reviews",  val:myBookings.filter(b=>b.status==="completed").length, col:C.green, onPress:null},
            ].map(s=>(
              <TouchableOpacity key={s.label} onPress={s.onPress}
                style={{flex:1,backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:12,padding:12,alignItems:"center"}}>
                <Text style={{fontSize:20,fontWeight:"800",color:s.col}}>{s.val}</Text>
                <Text style={{fontSize:10,color:C.sub,marginTop:2}}>{s.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{gap:10,marginBottom:20}}>
            {MENU_ITEMS.map(m=>(
              <TouchableOpacity key={m.title} onPress={m.onPress}
                style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:14,flexDirection:"row",alignItems:"center",gap:12}}>
                <View style={{width:40,height:40,borderRadius:20,backgroundColor:m.col+"18",alignItems:"center",justifyContent:"center",flexShrink:0}}>
                  <Text style={{fontSize:18}}>{m.icon}</Text>
                </View>
                <View style={{flex:1}}>
                  <Text style={{fontSize:13,fontWeight:"600",color:C.text}}>{m.title}</Text>
                  <Text style={{fontSize:11,color:C.sub,marginTop:1}}>{m.sub}</Text>
                </View>
                <Text style={{fontSize:14,color:C.dim}}>›</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity onPress={()=>setShowLogout(true)}
            style={{flexDirection:"row",alignItems:"center",gap:12,backgroundColor:C.redDim,borderWidth:1,borderColor:C.red+"44",borderRadius:14,padding:16,marginBottom:12}}>
            <View style={{width:40,height:40,borderRadius:20,backgroundColor:C.red+"18",alignItems:"center",justifyContent:"center"}}>
              <Text style={{fontSize:18}}>🚪</Text>
            </View>
            <View style={{flex:1}}>
              <Text style={{fontSize:13,fontWeight:"700",color:C.red}}>Sign Out</Text>
              <Text style={{fontSize:11,color:C.sub,marginTop:1}}>Log out of your account</Text>
            </View>
            <Text style={{fontSize:14,color:C.red}}>›</Text>
          </TouchableOpacity>

          <Text style={{fontSize:10,color:C.dim,textAlign:"center",marginBottom:8}}>
            SnapSphere v2.3.0 · AI-Powered · Made in Pakistan 🇵🇰
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const SHOP_PRODUCTS = [
  { id:1,  name:"Canon EOS R50",         brand:"Canon",    category:"Cameras",      price:189999, originalPrice:210000, rating:4.8, reviews:124, stock:8,  badge:"Best Seller", img:"📷", color:"#8B4E2A", desc:"24.2MP Mirrorless camera, perfect for beginners and vloggers. Includes 18-45mm kit lens.", specs:["24.2MP APS-C CMOS","4K Video @ 30fps","Wi-Fi & Bluetooth","180° Flip Screen","ISO 100-32000"] },
  { id:2,  name:"Sony Alpha A7 III",      brand:"Sony",     category:"Cameras",      price:389999, originalPrice:420000, rating:4.9, reviews:89,  stock:3,  badge:"Pro Choice", img:"📸", color:"#2A5E8B", desc:"Full-frame mirrorless with exceptional low-light performance. Ideal for professional photography.", specs:["24.2MP Full-Frame","4K HDR Video","693 Phase-detect AF Points","ISO 50-204800","5-axis Stabilization"] },
  { id:3,  name:"Nikon Z30",              brand:"Nikon",    category:"Cameras",      price:149999, originalPrice:170000, rating:4.7, reviews:67,  stock:12, badge:"New",         img:"🎥", color:"#2A8B5E", desc:"Compact APS-C vlogging camera with flip screen and no viewfinder for a lighter body.", specs:["20.9MP APS-C","4K UHD Video","Flip Touchscreen","USB-C Charging","No Viewfinder"] },
  { id:4,  name:"GoPro Hero 12 Black",    brand:"GoPro",    category:"Cameras",      price:99999,  originalPrice:115000, rating:4.8, reviews:203, stock:20, badge:"Adventure",   img:"🎬", color:"#5E2A8B", desc:"Waterproof action camera with HyperSmooth 6.0 stabilization. Perfect for adventure photography.", specs:["5.3K @ 60fps","HyperSmooth 6.0","Waterproof 10m","Night Mode","Voice Control"] },
  { id:5,  name:"50mm f/1.8 STM",         brand:"Canon",    category:"Lenses",       price:34999,  originalPrice:40000,  rating:4.9, reviews:312, stock:15, badge:"Must Have",   img:"🔭", color:"#8B2A5E", desc:"Sharp, fast 50mm prime lens. Perfect for portraits with beautiful bokeh at f/1.8.", specs:["50mm Focal Length","f/1.8 Aperture","STM Motor","Canon EF Mount","67mm Filter Size"] },
  { id:6,  name:"24-70mm f/2.8 GM",       brand:"Sony",     category:"Lenses",       price:249999, originalPrice:280000, rating:4.9, reviews:78,  stock:4,  badge:"Pro",         img:"🔬", color:"#5E7A2A", desc:"Professional standard zoom lens with constant f/2.8 aperture. Sony G Master quality.", specs:["24-70mm Zoom","f/2.8 Constant","XA Element","OSS Stabilization","Sony E-Mount"] },
  { id:7,  name:"85mm f/1.4 Portrait",    brand:"Sigma",    category:"Lenses",       price:89999,  originalPrice:105000, rating:4.8, reviews:156, stock:6,  badge:"Portrait",    img:"🌸", color:"#8B4E2A", desc:"Stunning portrait lens with Art series quality. Creates creamy bokeh at f/1.4.", specs:["85mm Focal Length","f/1.4 Aperture","Art Series","Multi-Mount","Weather Sealed"] },
  { id:8,  name:"Joby GorillaPod 3K",     brand:"Joby",     category:"Accessories",  price:12999,  originalPrice:15000,  rating:4.7, reviews:445, stock:30, badge:"Flexible",    img:"🦾", color:"#2A5E8B", desc:"Flexible tripod that wraps around any surface. Supports up to 3kg. Perfect for vlogging.", specs:["3kg Load Capacity","Flexible Legs","Quick Release","360° Ball Head","Works on Any Surface"] },
  { id:9,  name:"DJI OM 6 Gimbal",        brand:"DJI",      category:"Accessories",  price:49999,  originalPrice:58000,  rating:4.8, reviews:234, stock:10, badge:"Smooth",      img:"📱", color:"#2A8B5E", desc:"3-axis smartphone gimbal with intelligent shooting modes. Works with all major phones.", specs:["3-Axis Stabilization","ActiveTrack 6.0","Shot Guides","Magnetic Design","6h Battery"] },
  { id:10, name:"Manfrotto 055 Tripod",    brand:"Manfrotto",category:"Accessories",  price:39999,  originalPrice:48000,  rating:4.9, reviews:167, stock:7,  badge:"Sturdy",      img:"📐", color:"#5E2A8B", desc:"Professional carbon fiber tripod with 90° center column. Maximum stability for studio work.", specs:["Carbon Fiber","8kg Load Capacity","90° Column","Quick Release","165cm Max Height"] },
  { id:11, name:"Godox SL60W LED",         brand:"Godox",    category:"Lighting",     price:24999,  originalPrice:30000,  rating:4.7, reviews:389, stock:18, badge:"Studio",      img:"💡", color:"#E0973A", desc:"60W daylight balanced LED video light. Ideal for YouTube, studio and portrait photography.", specs:["60W Output","5600K Daylight","Bowens Mount","Wi-Fi App Control","Quiet Fan"] },
  { id:12, name:"Neewer Ring Light 18in",  brand:"Neewer",   category:"Lighting",     price:14999,  originalPrice:18000,  rating:4.6, reviews:521, stock:25, badge:"Selfie Pro",  img:"⭕", color:"#8B2A5E", desc:"18-inch LED ring light with phone holder and remote. Perfect for portraits and social media.", specs:["18in Ring Light","3 Color Modes","10 Brightness Levels","Phone Holder","USB Powered"] },
  { id:13, name:"Godox AD200 Pro Flash",   brand:"Godox",    category:"Lighting",     price:59999,  originalPrice:70000,  rating:4.9, reviews:143, stock:5,  badge:"Portable",    img:"⚡", color:"#5E7A2A", desc:"200Ws portable flash with bare bulb and speedlight heads. HSS and TTL supported.", specs:["200Ws Output","HSS & TTL","2900mAh Battery","500 Full Flashes","Dual Head Design"] },
  { id:14, name:"DJI Osmo Pocket 3",       brand:"DJI",      category:"Mobile",       price:79999,  originalPrice:92000,  rating:4.9, reviews:298, stock:9,  badge:"Compact",     img:"🎯", color:"#2A5E8B", desc:"Ultra-compact 3-axis gimbal camera with 1-inch sensor. 4K/120fps for buttery slow motion.", specs:["1-inch CMOS","4K @ 120fps","3-Axis Gimbal","2in Touchscreen","140min Battery"] },
  { id:15, name:"Moment Phone Lens Kit",   brand:"Moment",   category:"Mobile",       price:18999,  originalPrice:22000,  rating:4.7, reviews:187, stock:22, badge:"Creative",    img:"🔍", color:"#8B4E2A", desc:"Set of 3 clip-on lenses: wide, tele, and macro. Works with any smartphone.", specs:["Wide Angle Lens","Tele Lens","Macro Lens","Universal Clip","Includes Case"] },
  { id:16, name:"Rode Wireless GO II",     brand:"Rode",     category:"Mobile",       price:64999,  originalPrice:75000,  rating:4.9, reviews:267, stock:11, badge:"Audio Pro",   img:"🎙", color:"#2A8B5E", desc:"Dual wireless microphone system. 200m range, built-in recording. Perfect for vloggers.", specs:["Dual Transmitters","200m Range","Built-in Recording","32-bit Float","USB-C Charge"] },
  { id:17, name:"Lowepro ProTactic 450",   brand:"Lowepro",  category:"Bags",         price:29999,  originalPrice:36000,  rating:4.8, reviews:203, stock:13, badge:"Carry All",   img:"🎒", color:"#5E2A8B", desc:"Professional camera backpack with modular dividers. Fits DSLR + 3 lenses + 15in laptop.", specs:["DSLR + 3 Lenses","15in Laptop Slot","Rain Cover","Side Access","25L Capacity"] },
  { id:18, name:"SanDisk 256GB SD Card",   brand:"SanDisk",  category:"Bags",         price:8999,   originalPrice:11000,  rating:4.9, reviews:892, stock:50, badge:"Fast",        img:"💾", color:"#8B2A5E", desc:"V60 UHS-II SD card with 280MB/s read speed. Ideal for 4K and burst photography.", specs:["256GB Capacity","280MB/s Read","V60 UHS-II","Waterproof","Temperature Proof"] },
];

function ProductDetailModal({ product, visible, onClose, onAddToCart }) {
  const [qty,   setQty]   = useState(1);
  const [added, setAdded] = useState(false);
  const discount = Math.round(((product?.originalPrice - product?.price) / product?.originalPrice) * 100);

  const handleAdd = () => {
    onAddToCart(product, qty);
    setAdded(true);
    setTimeout(() => { setAdded(false); onClose(); }, 1000);
  };

  if (!product) return null;
  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <View style={{flex:1,backgroundColor:"#000000BB"}}>
        <TouchableOpacity style={{flex:1}} activeOpacity={1} onPress={onClose}/>
        <View style={{backgroundColor:C.surface,borderTopLeftRadius:24,borderTopRightRadius:24,borderWidth:1,borderColor:C.border,maxHeight:"88%"}}>
          <View style={{padding:20,flexDirection:"row",justifyContent:"space-between",alignItems:"center",borderBottomWidth:1,borderBottomColor:C.border}}>
            <Text style={{fontSize:16,fontWeight:"800",color:C.text,flex:1}}>{product.name}</Text>
            <TouchableOpacity onPress={onClose} style={{width:32,height:32,borderRadius:16,backgroundColor:C.card,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.border}}>
              <Text style={{color:C.text}}>✕</Text>
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={{padding:20,gap:16}}>
            <View style={{backgroundColor:product.color+"18",borderWidth:1.5,borderColor:product.color+"44",borderRadius:20,padding:30,alignItems:"center",justifyContent:"center"}}>
              <Text style={{fontSize:80}}>{product.img}</Text>
              <View style={{marginTop:12,backgroundColor:product.color,borderRadius:8,paddingHorizontal:12,paddingVertical:4}}>
                <Text style={{fontSize:10,fontWeight:"800",color:"#fff"}}>{product.badge}</Text>
              </View>
            </View>

            <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
              <View style={{backgroundColor:C.card,borderRadius:8,paddingHorizontal:10,paddingVertical:4,borderWidth:1,borderColor:C.border}}>
                <Text style={{fontSize:11,color:C.sub,fontWeight:"600"}}>{product.brand}</Text>
              </View>
              <View style={{flexDirection:"row",alignItems:"center",gap:6}}>
                <Text style={{color:C.gold,fontSize:14}}>★</Text>
                <Text style={{fontSize:13,fontWeight:"700",color:C.text}}>{product.rating}</Text>
                <Text style={{fontSize:11,color:C.sub}}>({product.reviews} reviews)</Text>
              </View>
            </View>

            <View style={{backgroundColor:C.card,borderRadius:14,padding:16,borderWidth:1,borderColor:C.gold+"33"}}>
              <View style={{flexDirection:"row",alignItems:"center",gap:10,marginBottom:4}}>
                <Text style={{fontSize:26,fontWeight:"800",color:C.gold}}>PKR {product.price.toLocaleString()}</Text>
                <View style={{backgroundColor:C.greenDim,borderRadius:6,paddingHorizontal:8,paddingVertical:3,borderWidth:1,borderColor:C.green+"44"}}>
                  <Text style={{fontSize:10,fontWeight:"700",color:C.green}}>{discount}% OFF</Text>
                </View>
              </View>
              <Text style={{fontSize:12,color:C.dim,textDecorationLine:"line-through"}}>PKR {product.originalPrice.toLocaleString()}</Text>
              <Text style={{fontSize:11,color:product.stock<=5?C.red:C.green,marginTop:6,fontWeight:"600"}}>
                {product.stock<=5 ? `⚠ Only ${product.stock} left!` : `✓ ${product.stock} in stock`}
              </Text>
            </View>

            <View>
              <Text style={{fontSize:13,fontWeight:"700",color:C.text,marginBottom:8}}>Description</Text>
              <Text style={{fontSize:13,color:C.sub,lineHeight:21}}>{product.desc}</Text>
            </View>

            <View style={{backgroundColor:C.card,borderRadius:14,padding:16,borderWidth:1,borderColor:C.border}}>
              <Text style={{fontSize:13,fontWeight:"700",color:C.text,marginBottom:12}}>Key Specs</Text>
              {product.specs.map((s,i) => (
                <View key={i} style={{flexDirection:"row",alignItems:"center",gap:8,paddingVertical:6,borderBottomWidth:i<product.specs.length-1?1:0,borderBottomColor:C.border}}>
                  <View style={{width:6,height:6,borderRadius:3,backgroundColor:C.gold}}/>
                  <Text style={{fontSize:12,color:C.sub}}>{s}</Text>
                </View>
              ))}
            </View>

            <View style={{flexDirection:"row",alignItems:"center",justifyContent:"space-between"}}>
              <Text style={{fontSize:13,fontWeight:"700",color:C.text}}>Quantity</Text>
              <View style={{flexDirection:"row",alignItems:"center",gap:0,backgroundColor:C.card,borderRadius:12,borderWidth:1,borderColor:C.border,overflow:"hidden"}}>
                <TouchableOpacity onPress={()=>setQty(Math.max(1,qty-1))}
                  style={{width:40,height:40,alignItems:"center",justifyContent:"center",borderRightWidth:1,borderRightColor:C.border}}>
                  <Text style={{fontSize:18,color:C.text,fontWeight:"700"}}>−</Text>
                </TouchableOpacity>
                <View style={{width:50,alignItems:"center"}}>
                  <Text style={{fontSize:15,fontWeight:"800",color:C.text}}>{qty}</Text>
                </View>
                <TouchableOpacity onPress={()=>setQty(Math.min(product.stock,qty+1))}
                  style={{width:40,height:40,alignItems:"center",justifyContent:"center",borderLeftWidth:1,borderLeftColor:C.border}}>
                  <Text style={{fontSize:18,color:C.text,fontWeight:"700"}}>+</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
              <Text style={{fontSize:13,color:C.sub}}>Total ({qty} item{qty>1?"s":""})</Text>
              <Text style={{fontSize:18,fontWeight:"800",color:C.gold}}>PKR {(product.price*qty).toLocaleString()}</Text>
            </View>

            <TouchableOpacity onPress={handleAdd}
              style={{paddingVertical:15,borderRadius:14,backgroundColor:added?C.green:C.gold,alignItems:"center",flexDirection:"row",justifyContent:"center",gap:8}}>
              <Text style={{fontSize:16}}>{added?"✓":"🛒"}</Text>
              <Text style={{fontSize:15,fontWeight:"800",color:C.bg}}>{added?"Added to Cart!":"Add to Cart"}</Text>
            </TouchableOpacity>

            <View style={{backgroundColor:C.card,borderRadius:12,padding:14,flexDirection:"row",gap:10,borderWidth:1,borderColor:C.border}}>
              <Text style={{fontSize:18}}>🚚</Text>
              <View style={{flex:1}}>
                <Text style={{fontSize:12,fontWeight:"700",color:C.text}}>Free Delivery in Pakistan</Text>
                <Text style={{fontSize:11,color:C.sub,marginTop:2}}>3-5 business days · Cash on Delivery available</Text>
              </View>
            </View>
            <View style={{height:10}}/>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function CartModal({ visible, onClose, cartItems, onUpdateQty, onRemove, onCheckout }) {
  const total = cartItems.reduce((s, i) => s + i.price * i.qty, 0);
  const count = cartItems.reduce((s, i) => s + i.qty, 0);

  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      <View style={{flex:1,backgroundColor:"#000000BB"}}>
        <TouchableOpacity style={{flex:1}} activeOpacity={1} onPress={onClose}/>
        <View style={{backgroundColor:C.surface,borderTopLeftRadius:24,borderTopRightRadius:24,borderWidth:1,borderColor:C.border,maxHeight:"80%"}}>
          <View style={{padding:20,flexDirection:"row",justifyContent:"space-between",alignItems:"center",borderBottomWidth:1,borderBottomColor:C.border}}>
            <View>
              <Text style={{fontSize:18,fontWeight:"800",color:C.text}}>🛒 My Cart</Text>
              <Text style={{fontSize:11,color:C.sub,marginTop:2}}>{count} item{count!==1?"s":""}</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{width:32,height:32,borderRadius:16,backgroundColor:C.card,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.border}}>
              <Text style={{color:C.text}}>✕</Text>
            </TouchableOpacity>
          </View>
          {cartItems.length===0 ? (
            <View style={{alignItems:"center",paddingVertical:60}}>
              <Text style={{fontSize:48,marginBottom:14}}>🛒</Text>
              <Text style={{fontSize:16,color:C.text,fontWeight:"700",marginBottom:6}}>Cart is empty</Text>
              <Text style={{fontSize:13,color:C.sub}}>Add products from the Shop</Text>
            </View>
          ) : (
            <>
              <ScrollView contentContainerStyle={{padding:16,gap:10}}>
                {cartItems.map(item=>(
                  <View key={item.id} style={{backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:14,padding:14,flexDirection:"row",gap:12,alignItems:"center"}}>
                    <View style={{width:52,height:52,borderRadius:12,backgroundColor:item.color+"22",alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:item.color+"44"}}>
                      <Text style={{fontSize:26}}>{item.img}</Text>
                    </View>
                    <View style={{flex:1}}>
                      <Text style={{fontSize:13,fontWeight:"700",color:C.text}} numberOfLines={1}>{item.name}</Text>
                      <Text style={{fontSize:11,color:C.gold,fontWeight:"700",marginTop:2}}>PKR {(item.price*item.qty).toLocaleString()}</Text>
                      <View style={{flexDirection:"row",alignItems:"center",gap:8,marginTop:6}}>
                        <TouchableOpacity onPress={()=>onUpdateQty(item.id,item.qty-1)}
                          style={{width:26,height:26,borderRadius:8,backgroundColor:C.surface,borderWidth:1,borderColor:C.border,alignItems:"center",justifyContent:"center"}}>
                          <Text style={{color:C.text,fontWeight:"700"}}>−</Text>
                        </TouchableOpacity>
                        <Text style={{fontSize:13,fontWeight:"800",color:C.text,minWidth:20,textAlign:"center"}}>{item.qty}</Text>
                        <TouchableOpacity onPress={()=>onUpdateQty(item.id,item.qty+1)}
                          style={{width:26,height:26,borderRadius:8,backgroundColor:C.surface,borderWidth:1,borderColor:C.border,alignItems:"center",justifyContent:"center"}}>
                          <Text style={{color:C.text,fontWeight:"700"}}>+</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                    <TouchableOpacity onPress={()=>onRemove(item.id)}
                      style={{width:30,height:30,borderRadius:10,backgroundColor:C.redDim,alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:C.red+"44"}}>
                      <Text style={{color:C.red,fontSize:14}}>✕</Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </ScrollView>
              <View style={{padding:16,borderTopWidth:1,borderTopColor:C.border,gap:12}}>
                <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
                  <Text style={{fontSize:14,color:C.sub}}>Subtotal</Text>
                  <Text style={{fontSize:14,fontWeight:"700",color:C.text}}>PKR {total.toLocaleString()}</Text>
                </View>
                <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
                  <Text style={{fontSize:14,color:C.sub}}>Delivery</Text>
                  <Text style={{fontSize:14,fontWeight:"700",color:C.green}}>Free 🚚</Text>
                </View>
                <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",paddingTop:10,borderTopWidth:1,borderTopColor:C.border}}>
                  <Text style={{fontSize:16,fontWeight:"800",color:C.text}}>Total</Text>
                  <Text style={{fontSize:20,fontWeight:"800",color:C.gold}}>PKR {total.toLocaleString()}</Text>
                </View>
                <TouchableOpacity onPress={onCheckout}
                  style={{paddingVertical:14,borderRadius:14,backgroundColor:C.gold,alignItems:"center",flexDirection:"row",justifyContent:"center",gap:8}}>
                  <Text style={{fontSize:16}}>✓</Text>
                  <Text style={{fontSize:15,fontWeight:"800",color:C.bg}}>Place Order · PKR {total.toLocaleString()}</Text>
                </TouchableOpacity>
                <Text style={{fontSize:10,color:C.dim,textAlign:"center"}}>💳 Cash on Delivery · Bank Transfer · JazzCash · EasyPaisa</Text>
              </View>
            </>
          )}
        </View>
      </View>
    </Modal>
  );
}

// ── FIX: OrderSuccessModal — removed literal newline inside JSX braces ─────────
function OrderSuccessModal({ visible, onClose, total }) {
  const scale  = useRef(new Animated.Value(0)).current;
  const opacity= useRef(new Animated.Value(0)).current;
  useEffect(()=>{
    if(visible){
      Animated.parallel([
        Animated.spring(scale,{toValue:1,tension:60,friction:6,useNativeDriver:true}),
        Animated.timing(opacity,{toValue:1,duration:300,useNativeDriver:true}),
      ]).start();
    }
  },[visible]);

  return (
    <Modal transparent animationType="fade" visible={visible} onRequestClose={onClose}>
      <View style={{flex:1,backgroundColor:"#000000CC",alignItems:"center",justifyContent:"center",padding:24}}>
        <Animated.View style={{backgroundColor:C.card,borderRadius:24,padding:28,width:"100%",alignItems:"center",borderWidth:1.5,borderColor:C.gold+"44",opacity,transform:[{scale}]}}>
          <View style={{width:80,height:80,borderRadius:40,backgroundColor:C.greenDim,borderWidth:2,borderColor:C.green+"44",alignItems:"center",justifyContent:"center",marginBottom:16}}>
            <Text style={{fontSize:38}}>✅</Text>
          </View>
          <Text style={{fontSize:11,color:C.gold,letterSpacing:3,textTransform:"uppercase",marginBottom:6}}>Order Placed!</Text>
          <Text style={{fontSize:24,fontWeight:"800",color:C.text,marginBottom:8,textAlign:"center"}}>Your order is confirmed 🎉</Text>
          {/* ✅ FIX: split into two separate Text lines instead of {"<newline>"} */}
          <Text style={{fontSize:13,color:C.sub,textAlign:"center",lineHeight:20,marginBottom:20}}>
            {"Total: "}
            <Text style={{color:C.gold,fontWeight:"700"}}>PKR {total?.toLocaleString()}</Text>
            {"\nExpected delivery in 3-5 business days."}
          </Text>
          {[
            {icon:"📦",label:"Processing",done:true},
            {icon:"🚚",label:"Shipped",done:false},
            {icon:"🏠",label:"Delivered",done:false},
          ].map((s,i)=>(
            <View key={i} style={{flexDirection:"row",alignItems:"center",gap:10,width:"100%",marginBottom:8}}>
              <View style={{width:32,height:32,borderRadius:16,backgroundColor:s.done?C.greenDim:C.card,borderWidth:1,borderColor:s.done?C.green+"44":C.border,alignItems:"center",justifyContent:"center"}}>
                <Text style={{fontSize:14}}>{s.icon}</Text>
              </View>
              <Text style={{fontSize:13,color:s.done?C.green:C.sub,fontWeight:s.done?"700":"400"}}>{s.label}</Text>
              {s.done && <Text style={{fontSize:11,color:C.green,marginLeft:"auto"}}>✓ Done</Text>}
            </View>
          ))}
          <TouchableOpacity onPress={onClose}
            style={{paddingVertical:14,paddingHorizontal:40,borderRadius:14,backgroundColor:C.gold,alignItems:"center",marginTop:12,width:"100%"}}>
            <Text style={{fontSize:14,fontWeight:"800",color:C.bg}}>Continue Shopping →</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>
    </Modal>
  );
}

function ShopScreen({ currentUser }) {
  const CATS = ["All","Cameras","Lenses","Accessories","Lighting","Mobile","Bags"];
  const [cat,         setCat]         = useState("All");
  const [search,      setSearch]      = useState("");
  const [sort,        setSort]        = useState("Popular");
  const [selProduct,  setSelProduct]  = useState(null);
  const [showCart,    setShowCart]    = useState(false);
  const [showOrder,   setShowOrder]   = useState(false);
  const [cartItems,   setCartItems]   = useState([]);
  const [orderTotal,  setOrderTotal]  = useState(0);
  const [toast,       setToast]       = useState(null);
  const [wishIds,     setWishIds]     = useState([]);

  const cartCount = cartItems.reduce((s,i)=>s+i.qty,0);

  const filtered = SHOP_PRODUCTS
    .filter(p => cat==="All" || p.category===cat)
    .filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.brand.toLowerCase().includes(search.toLowerCase()))
    .sort((a,b) => {
      if(sort==="Price Low") return a.price - b.price;
      if(sort==="Price High") return b.price - a.price;
      if(sort==="Rating") return b.rating - a.rating;
      return b.reviews - a.reviews;
    });

  const addToCart = (product, qty=1) => {
    setCartItems(prev => {
      const ex = prev.find(i=>i.id===product.id);
      if(ex) return prev.map(i=>i.id===product.id?{...i,qty:i.qty+qty}:i);
      return [...prev,{...product,qty}];
    });
    setToast({message:`✓ ${product.name} added to cart!`,type:"success"});
  };

  const updateQty = (id, qty) => {
    if(qty<=0){ removeItem(id); return; }
    setCartItems(prev=>prev.map(i=>i.id===id?{...i,qty}:i));
  };

  const removeItem = (id) => setCartItems(prev=>prev.filter(i=>i.id!==id));

  const toggleWish = (id) => setWishIds(prev=>prev.includes(id)?prev.filter(x=>x!==id):[...prev,id]);

  const checkout = () => {
    const total = cartItems.reduce((s,i)=>s+i.price*i.qty,0);
    setOrderTotal(total);
    setShowCart(false);
    setCartItems([]);
    setTimeout(()=>setShowOrder(true),300);
  };

  return (
    <View style={{flex:1,backgroundColor:C.bg}}>
      {toast && <Toast message={toast.message} type={toast.type} onDone={()=>setToast(null)}/>}

      <ProductDetailModal
        product={selProduct} visible={!!selProduct}
        onClose={()=>setSelProduct(null)}
        onAddToCart={addToCart}/>
      <CartModal
        visible={showCart} onClose={()=>setShowCart(false)}
        cartItems={cartItems} onUpdateQty={updateQty}
        onRemove={removeItem} onCheckout={checkout}/>
      <OrderSuccessModal
        visible={showOrder} onClose={()=>setShowOrder(false)}
        total={orderTotal}/>

      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={{padding:20,paddingTop:24,flexDirection:"row",justifyContent:"space-between",alignItems:"flex-start"}}>
          <View>
            <Text style={{fontSize:11,letterSpacing:1.8,color:C.gold,textTransform:"uppercase",marginBottom:4}}>Photography</Text>
            <Text style={{fontSize:26,fontWeight:"400",color:C.text}}>
              Gear <Text style={{color:C.gold,fontStyle:"italic"}}>Shop</Text>
            </Text>
            <Text style={{fontSize:11,color:C.sub,marginTop:3}}>{SHOP_PRODUCTS.length} products available</Text>
          </View>
          <TouchableOpacity onPress={()=>setShowCart(true)} style={{position:"relative",padding:4}}>
            <View style={{width:46,height:46,borderRadius:23,backgroundColor:C.card,borderWidth:1.5,borderColor:C.gold+"44",alignItems:"center",justifyContent:"center"}}>
              <Text style={{fontSize:22}}>🛒</Text>
            </View>
            {cartCount>0 && (
              <View style={{position:"absolute",top:0,right:0,minWidth:20,height:20,borderRadius:10,backgroundColor:C.gold,alignItems:"center",justifyContent:"center",borderWidth:2,borderColor:C.bg,paddingHorizontal:4}}>
                <Text style={{fontSize:10,fontWeight:"800",color:C.bg}}>{cartCount}</Text>
              </View>
            )}
          </TouchableOpacity>
        </View>

        <View style={{marginHorizontal:20,marginBottom:14}}>
          <View style={{backgroundColor:C.card,borderWidth:1,borderColor:C.borderMid,borderRadius:14,padding:12,flexDirection:"row",alignItems:"center",gap:10}}>
            <Text style={{fontSize:15}}>🔍</Text>
            <TextInput value={search} onChangeText={setSearch}
              placeholder="Search cameras, lenses, accessories..."
              placeholderTextColor={C.dim}
              style={{flex:1,color:C.text,fontSize:13}}/>
            {!!search && <TouchableOpacity onPress={()=>setSearch("")}><Text style={{color:C.dim,fontSize:16}}>✕</Text></TouchableOpacity>}
          </View>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom:12}} contentContainerStyle={{paddingHorizontal:20,gap:8}}>
          {CATS.map(c=>(
            <TouchableOpacity key={c} onPress={()=>setCat(c)}
              style={{paddingHorizontal:16,paddingVertical:8,borderRadius:20,marginRight:8,backgroundColor:cat===c?C.gold:C.card,borderWidth:1,borderColor:cat===c?C.gold:C.border}}>
              <Text style={{fontSize:11,fontWeight:"600",color:cat===c?C.bg:C.sub}}>{c}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",paddingHorizontal:20,marginBottom:14}}>
          <Text style={{fontSize:11,color:C.sub}}>{filtered.length} products</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            {["Popular","Rating","Price Low","Price High"].map(s=>(
              <TouchableOpacity key={s} onPress={()=>setSort(s)}
                style={{paddingHorizontal:10,paddingVertical:5,borderRadius:8,marginLeft:6,backgroundColor:sort===s?C.gold:C.card,borderWidth:1,borderColor:sort===s?C.gold:C.border}}>
                <Text style={{fontSize:10,fontWeight:"600",color:sort===s?C.bg:C.sub}}>{s}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>

        <View style={{paddingHorizontal:16,flexDirection:"row",flexWrap:"wrap",gap:10,marginBottom:20}}>
          {filtered.map(p=>{
            const disc = Math.round(((p.originalPrice-p.price)/p.originalPrice)*100);
            const wished = wishIds.includes(p.id);
            return (
              <TouchableOpacity key={p.id} onPress={()=>setSelProduct(p)}
                style={{width:(width-42)/2,backgroundColor:C.card,borderWidth:1,borderColor:C.border,borderRadius:16,overflow:"hidden"}}>
                <View style={{backgroundColor:p.color+"14",padding:20,alignItems:"center",position:"relative"}}>
                  <Text style={{fontSize:52}}>{p.img}</Text>
                  <View style={{position:"absolute",top:8,left:8,backgroundColor:p.color,borderRadius:6,paddingHorizontal:7,paddingVertical:3}}>
                    <Text style={{fontSize:8,fontWeight:"800",color:"#fff"}}>{p.badge}</Text>
                  </View>
                  <TouchableOpacity onPress={()=>toggleWish(p.id)}
                    style={{position:"absolute",top:6,right:6,width:28,height:28,borderRadius:14,backgroundColor:wished?C.red+"22":C.card,borderWidth:1,borderColor:wished?C.red+"44":C.border,alignItems:"center",justifyContent:"center"}}>
                    <Text style={{fontSize:13,color:wished?C.red:C.dim}}>{wished?"❤":"♡"}</Text>
                  </TouchableOpacity>
                  <View style={{position:"absolute",bottom:8,right:8,backgroundColor:C.greenDim,borderRadius:6,paddingHorizontal:6,paddingVertical:2,borderWidth:1,borderColor:C.green+"44"}}>
                    <Text style={{fontSize:9,fontWeight:"700",color:C.green}}>{disc}% OFF</Text>
                  </View>
                </View>
                <View style={{padding:12}}>
                  <Text style={{fontSize:9,color:C.sub,letterSpacing:0.5,textTransform:"uppercase",marginBottom:4}}>{p.brand}</Text>
                  <Text style={{fontSize:12,fontWeight:"700",color:C.text,lineHeight:17,marginBottom:6}} numberOfLines={2}>{p.name}</Text>
                  <View style={{flexDirection:"row",alignItems:"center",gap:4,marginBottom:8}}>
                    <Text style={{fontSize:10,color:C.gold}}>★ {p.rating}</Text>
                    <Text style={{fontSize:9,color:C.dim}}>({p.reviews})</Text>
                    {p.stock<=5 && <Text style={{fontSize:9,color:C.red,marginLeft:"auto"}}>Only {p.stock} left</Text>}
                  </View>
                  <Text style={{fontSize:13,fontWeight:"800",color:C.gold}}>PKR {(p.price/1000).toFixed(0)}k</Text>
                  <Text style={{fontSize:10,color:C.dim,textDecorationLine:"line-through"}}>PKR {(p.originalPrice/1000).toFixed(0)}k</Text>
                  <TouchableOpacity onPress={()=>{ addToCart(p,1);}}
                    style={{marginTop:10,paddingVertical:8,borderRadius:10,backgroundColor:C.gold,alignItems:"center",flexDirection:"row",justifyContent:"center",gap:6}}>
                    <Text style={{fontSize:12}}>🛒</Text>
                    <Text style={{fontSize:11,fontWeight:"700",color:C.bg}}>Add to Cart</Text>
                  </TouchableOpacity>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>

        {filtered.length===0 && (
          <View style={{alignItems:"center",paddingVertical:60}}>
            <Text style={{fontSize:40,marginBottom:14}}>🔍</Text>
            <Text style={{fontSize:15,color:C.text,fontWeight:"700",marginBottom:6}}>No products found</Text>
            <Text style={{fontSize:12,color:C.sub}}>Try a different search or category</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const NAV_ITEMS = [
  { id:"Home",      icon:"🏠", label:"Home"      },
  { id:"Explore",   icon:"🔭", label:"Explore"   },
  { id:"Shop",      icon:"🛒", label:"Shop"      },
  { id:"Bookings",  icon:"📅", label:"Bookings"  },
  { id:"Profile",   icon:"👤", label:"Profile"   },
];

export default function App() {
  const [authStage,   setAuthStage]   = useState("splash");
  const [currentUser, setCurrentUser] = useState(null);
  const [screen,      setScreen]      = useState("Home");
  const [selP,        setSelP]        = useState(null);
  const [booking,     setBooking]     = useState(null);
  const [chatPhotog,  setChatPhotog]  = useState(null);
  const [showNotifs,  setShowNotifs]  = useState(false);

  const handleLogin = (user) => {
    setCurrentUser({ ...user, activeRole: user.role === "admin" ? "buyer" : user.role });
    setAuthStage("app");
  };
  const handleLogout = () => {
    setCurrentUser(null); setScreen("Home"); setSelP(null); setBooking(null);
    setChatPhotog(null); setAuthStage("login");
  };
  const handleSwitchRole = (newRole) => {
    setCurrentUser(prev => ({ ...prev, activeRole: newRole })); setSelP(null); setBooking(null);
  };

  if (authStage==="splash") return (<><StatusBar barStyle="light-content" backgroundColor={C.bg}/><SplashScreen onDone={()=>setAuthStage("login")}/></>);
  if (authStage==="login")  return (<SafeAreaView style={{flex:1,backgroundColor:C.bg}}><StatusBar barStyle="light-content" backgroundColor={C.bg}/><LoginScreen onLogin={handleLogin} onGoRegister={()=>setAuthStage("register")} onGoForgot={()=>setAuthStage("forgot")}/></SafeAreaView>);
  if (authStage==="register") return (<SafeAreaView style={{flex:1,backgroundColor:C.bg}}><StatusBar barStyle="light-content" backgroundColor={C.bg}/><RegisterScreen onRegister={()=>setAuthStage("login")} onGoLogin={()=>setAuthStage("login")}/></SafeAreaView>);
  if (authStage==="forgot")   return (<SafeAreaView style={{flex:1,backgroundColor:C.bg}}><StatusBar barStyle="light-content" backgroundColor={C.bg}/><ForgotPasswordScreen onGoLogin={()=>setAuthStage("login")}/></SafeAreaView>);

  const renderScreen = () => {
    if (chatPhotog) return <ChatScreen currentUser={currentUser} photographer={chatPhotog} onBack={()=>setChatPhotog(null)}/>;
    if (booking) return <BookingScreen p={booking} onBack={()=>setBooking(null)} onDone={()=>{setBooking(null);setSelP(null);setScreen("Bookings");}} currentUser={currentUser}/>;
    if (selP)    return <PhotogProfile p={selP} onBack={()=>setSelP(null)} onBook={p=>setBooking(p)} onChat={p=>{setChatPhotog(p);}}/>;
    switch(screen) {
      case "Home":      return <HomeScreen      onNavigate={setScreen} onViewPhotog={p=>setSelP(p)} currentUser={currentUser} onSwitchRole={handleSwitchRole} onShowNotifs={()=>setShowNotifs(true)}/>;
      case "Explore":   return <ExploreScreen   onViewPhotog={p=>setSelP(p)} currentUser={currentUser}/>;
      case "Bookings":  return <BookingsScreen  onNavigate={setScreen} currentUser={currentUser}/>;
      case "Shop":      return <ShopScreen      currentUser={currentUser}/>;
      case "Dashboard": return <DashboardScreen currentUser={currentUser}/>;
      case "Profile":   return <ProfileScreen   onNavigate={setScreen} currentUser={currentUser} onLogout={handleLogout} onSwitchRole={handleSwitchRole} onUpdateUser={(updates)=>setCurrentUser(prev=>({...prev,...updates}))}/>;
      default:          return <HomeScreen      onNavigate={setScreen} onViewPhotog={setSelP} currentUser={currentUser} onSwitchRole={handleSwitchRole} onShowNotifs={()=>setShowNotifs(true)}/>;
    }
  };

  const activeTab = booking || selP || chatPhotog ? null : screen;
  return (
    <SafeAreaView style={{flex:1,backgroundColor:C.bg}}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg}/>
      {currentUser && (
        <NotificationsPanel
          userId={currentUser.id}
          visible={showNotifs}
          onClose={()=>setShowNotifs(false)}
        />
      )}
      <View style={{flex:1}}>{renderScreen()}</View>
      {!chatPhotog && (
        <View style={{height:64,backgroundColor:C.surface,borderTopWidth:1,borderTopColor:C.border,flexDirection:"row"}}>
          {NAV_ITEMS.map(item=>(
            <TouchableOpacity key={item.id} onPress={()=>{setSelP(null);setBooking(null);setChatPhotog(null);setScreen(item.id);}} style={{flex:1,alignItems:"center",justifyContent:"center",gap:3}}>
              <Text style={{fontSize:20,opacity:activeTab===item.id?1:0.35}}>{item.icon}</Text>
              <Text style={{fontSize:9,fontWeight:"600",letterSpacing:0.6,textTransform:"uppercase",color:activeTab===item.id?C.gold:C.dim}}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </SafeAreaView>
  );
}