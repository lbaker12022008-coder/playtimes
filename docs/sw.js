/* PlayTime notifications. Nothing is cached: a cached page here would
   mean stale player counts, which is worse than no page. */
self.addEventListener('install',function(e){self.skipWaiting()});
self.addEventListener('activate',function(e){e.waitUntil(self.clients.claim())});
self.addEventListener('push',function(e){
var d={};try{d=e.data.json()}catch(err){}
e.waitUntil(self.registration.showNotification(d.title||'PlayTime',{
body:d.body||'',icon:'/icon-192.png',badge:'/icon-192.png',
tag:d.tag||'playtime',data:{url:d.url||'/'}}))});
/* Tapping it should land on the game's page, and should re-use a tab that is
   already open on it rather than piling up windows. */
self.addEventListener('notificationclick',function(e){
e.notification.close();
var want=(e.notification.data&&e.notification.data.url)||'/';
e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true})
.then(function(list){
for(var i=0;i<list.length;i++){
if(list[i].url.indexOf(want)>-1&&'focus' in list[i])return list[i].focus()}
if(self.clients.openWindow)return self.clients.openWindow(want)}))});
