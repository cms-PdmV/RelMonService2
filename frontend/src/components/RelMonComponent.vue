<template>
  <div>
    <div class="elevation-3 mb-2 pl-3 pr-3 pt-2 pb-2" style="background: white; position: relative;">
      <v-row>
        <v-col cols=12>
          <span class="bigger-text">{{relmonData.name}}</span>
        </v-col>
      </v-row>
      <v-row>
        <v-col lg=5 md=6 sm=6 cols=12>
          Details
          <ul>
            <li><span class="font-weight-light">ID:</span> {{relmonData.id}}</li>
            <li><span class="font-weight-light">Status:</span> <span :title="'HTCondor Status: ' + relmonData.condor_status + '\nHTCondor ID: ' + relmonData.condor_id">{{relmonData.status}}</span> <span v-if="relmonData.status == 'done'">
              | <a target="_blank" :href="'https://cms-pdmv-prod.web.cern.ch/relmon?q=' + relmonData.name">go to reports</a>
            </span></li>
            <li><span class="font-weight-light">Last update:</span> {{niceDate(relmonData.last_update)}}</li>
          </ul>
          Progress
          <ul>
            <li><span class="font-weight-light">Download:</span>
              <v-progress-linear :value="relmonData.downloaded_relvals / relmonData.total_relvals * 100"
                                 color="success"
                                 height="16"
                                 class="elevation-1 progress-bar">
                <small><strong>{{ Math.ceil(relmonData.downloaded_relvals / relmonData.total_relvals * 100) }}%</strong></small>
              </v-progress-linear>
            </li>
            <li><span class="font-weight-light">Comparison:</span>
              <v-progress-linear :value="(relmonData.compared_relvals / relmonData.total_relvals * 99) + (relmonData.status == 'done' ? 1 : 0)"
                                 color="primary"
                                 height="16"
                                 class="elevation-1 progress-bar">
                <small><strong>{{ Math.ceil(relmonData.compared_relvals / relmonData.total_relvals * 99) + (relmonData.status == 'done' ? 1 : 0) }}%</strong></small>
              </v-progress-linear>
            </li>
          </ul>
          <div v-if="userInfo.authorized">
            Actions
            <br>
            <v-btn small class="ma-1" color="primary" @click="editRelmon(relmonData)">Edit</v-btn>
            <v-btn small class="ma-1" color="error" @click="resetConformationOverlay = true">Reset</v-btn>
            <v-btn small class="ma-1" color="error" @click="deleteConformationOverlay = true">Delete</v-btn>
          </div>
        </v-col>
        <v-col lg=7 md=6 sm=6 cols=12>
          Categories
          <ul>
            <li v-for="category in relmonData.categories" v-if="category.reference.length || category.target.length" :key="category.name">
              <span class="font-weight-light">{{category.name}}</span> - {{category.status}} <span class="font-weight-light">| HLT:</span> {{category.hlt}} <span class="font-weight-light">| pairing:</span> {{category.automatic_pairing ? 'auto' : 'manual'}}
              <ul>
                <li>
                  <span class="font-weight-light">References</span>
                  <span class="font-weight-light"> - total:</span> {{category.reference.length}}
                  <!-- <span class="font-weight-light"> | size:</span>&nbsp;{{Math.round((category.reference_total_size / 1024.0 / 1024.0) * 10) / 10}}MB -->
                  <span v-for="(value, key) in category.reference_status" :key="key">
                    <span class="font-weight-light">&nbsp;|</span><span class="font-weight-light" :class="key | statusToColor">&nbsp;{{key}}:&nbsp;</span><span :class="key | statusToColor">{{value}}</span>
                  </span>
                </li>
                <li>
                  <span class="font-weight-light">Targets</span>
                  <span class="font-weight-light"> - total:</span> {{category.target.length}}
                  <!-- <span class="font-weight-light"> | size:</span>&nbsp;{{Math.round((category.target_total_size / 1024.0 / 1024.0) * 10) / 10}}MB -->
                  <span v-for="(value, key) in category.target_status" :key="key">
                    <span class="font-weight-light">&nbsp;|</span><span class="font-weight-light" :class="key | statusToColor">&nbsp;{{key}}:&nbsp;</span><span :class="key | statusToColor">{{value}}</span>
                  </span>
                </li>
              </ul>
            </li>
          </ul>
          <v-btn small class="ma-1" color="primary" @click="detailedView = true; detailedViewFileInfo = false;">Open detailed view</v-btn>
        </v-col>

        <v-overlay :absolute="false"
                   :opacity="0.95"
                   :z-index="3"
                   :value="resetConformationOverlay"
                   style="text-align: center">
          This will reset {{relmonData.name}}. All progress will be lost and RelMon will be redone from scratch.<br>Are you sure you want to reset {{relmonData.name}}?<br>
          <v-btn color="error"
                 class="ma-1"
                 small
                 v-if="!isRefreshing"
                 @click="resetRelmon(relmonData)">
            Reset
          </v-btn>
          <v-btn color="primary"
                 class="ma-1"
                 small
                 v-if="!isRefreshing"
                 @click="resetConformationOverlay = false">
            Cancel
          </v-btn>
          <v-progress-circular indeterminate
                               v-if="isRefreshing"
                               color="primary"></v-progress-circular>
        </v-overlay>

        <v-overlay :absolute="false"
                   :opacity="0.95"
                   :z-index="3"
                   :value="deleteConformationOverlay"
                   style="text-align: center">
          This will delete {{relmonData.name}}. Generated reports will stay unaffected, but RelMon will be forever removed from RelMon Service.<br>Are you sure you want to delete {{relmonData.name}}?<br>
          <v-btn color="error"
                 class="ma-1"
                 small
                 v-if="!isRefreshing"
                 @click="deleteRelmon(relmonData)">
            Delete
          </v-btn>
          <v-btn color="primary"
                 class="ma-1"
                 small
                 v-if="!isRefreshing"
                 @click="deleteConformationOverlay = false">
            Cancel
          </v-btn>
          <v-progress-circular indeterminate
                               v-if="isRefreshing"
                               color="primary"></v-progress-circular>
        </v-overlay>
      </v-row>
    </div>
    <v-dialog v-if="detailedView" v-model="detailedView">
      <v-card class="pa-4">
        <span class="font-weight-light bigger-text">Categories of</span> <span class="ml-2 bigger-text">{{relmonData.name}}</span>
        <v-switch v-model="detailedViewFileInfo" class="ma-2" label="Show file info"></v-switch>
        <div v-for="category in relmonData.categories" v-if="category.reference.length || category.target.length">
          <span class="font-weight-light bigger-text">{{category.name}}</span>

          <ul>
            <li><span class="font-weight-light">Status:</span> {{category.status}}</li>
            <li><span class="font-weight-light">HLT:</span> {{category.hlt}}</li>
            <li><span class="font-weight-light">Pairing:</span> {{category.automatic_pairing ? 'auto' : 'manual'}}</li>
          </ul>

          <small v-if="category.status == 'initial'" style="color:red">Note: RelVals in this category were not paired yet, they will be paired just before category is compared</small>
          <div class="table-wrapper">
            <table>
              <tr>
                <th colspan="2">
                  References <span class="font-weight-light">(total: </span>{{category.reference.length}} <span class="font-weight-light">| size: </span>{{niceSize(category.reference_size)}}<span class="font-weight-light">)</span>
                </th>
                <th colspan="2">
                  Targets <span class="font-weight-light">(total: </span>{{category.target.length}} <span class="font-weight-light">| size: </span>{{niceSize(category.target_size)}}<span class="font-weight-light">)</span>
                </th>
              </tr>
              <tr v-for="(pair, index) in getPairs(category)" :key="index">
                <td>
                  <span v-if="pair.reference">{{pair.reference.name}}</span>
                  <div class="small-font" v-if="detailedViewFileInfo && pair.reference && pair.reference.file_name">
                    <a :href="'https://cmsweb.cern.ch' + pair.reference.file_url">{{pair.reference.file_name}}</a>
                  </div>
                </td>

                <td class="file-info">
                  <div :class="pair.reference.status | statusToColor" v-if="pair.reference">{{pair.reference.status}}</div>
                  <div v-if="detailedViewFileInfo && pair.reference && pair.reference.events">{{pair.reference.events}} events</div>
                  <div v-if="detailedViewFileInfo && pair.reference">{{niceSize(pair.reference.file_size)}}</div>
                </td>

                <td>
                  <span v-if="pair.target">{{pair.target.name}}</span>
                  <div class="small-font" v-if="detailedViewFileInfo && pair.target && pair.target.file_name">
                    <a :href="'https://cmsweb.cern.ch' + pair.target.file_url">{{pair.target.file_name}}</a>
                  </div>
                </td>

                <td class="file-info">
                  <div :class="pair.target.status | statusToColor" v-if="pair.target">{{pair.target.status}}</div>
                  <div v-if="detailedViewFileInfo && pair.target && pair.target.events">{{pair.target.events}} events</div>
                  <div v-if="detailedViewFileInfo && pair.target">{{niceSize(pair.target.file_size)}}</div>
                </td>
              </tr>
            </table>
          </div>

        </div>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn small class="ma-1" color="primary" @click="detailedView = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>

import axios from 'axios'
import dateFormat from 'dateformat'

export default {
  name: 'RelMonComponent',
  data () {
    return {
      resetConformationOverlay: false,
      deleteConformationOverlay: false,
      isRefreshing: false,
      detailedView: false,
      detailedViewFileInfo: false,
      pairingCache: {},
    }
  },
  created () {

  },
  watch: {
  },
  filters: {
    statusToColor (status) {
      if (status.startsWith("no_") || status === 'failed') {
        return "red-text";
      }
      if (status === 'downloaded') {
        return "green-text";
      }
      if (status === 'initial') {
        return "gray-text";
      }
      if (status === 'downloading') {
        return "blinking-text";
      }
      return "";
    }
  },
  props: {
    relmonData: {
      type: Object,
      default: () => {}
    },
    userInfo: {
      type: Object,
      default: function () { return { 'name': '', 'authorized': false }; }
    }
  },
  components: {
  },
  methods: {
    editRelmon(relmon) {
      this.$emit('editRelmon', relmon)
    },
    resetRelmon(relmon) {
      let component = this;
      component.isRefreshing = true;
      axios.post('api/reset', {
        'id': component.relmonData.id
      }).then(response => {
        setTimeout(function(){
          component.refetchRelmons();
          component.resetConformationOverlay = false;
          component.isRefreshing = false;
        }, 5000);
      }).catch(error => {
        component.isRefreshing = false;
        alert('Error resetting RelMon, refresh the page and try again');
      });
    },
    deleteRelmon(relmon) {
      let component = this;
      component.isRefreshing = true;
      axios.delete('api/delete', { data:{
        'id': component.relmonData.id
      }
      }).then(response => {
        setTimeout(function(){
          component.refetchRelmons();
          component.deleteConformationOverlay = false;
          component.isRefreshing = false;
        }, 5000);
      }).catch(error => {
        component.isRefreshing = false;
        alert('Error deleting RelMon, refresh the page and try again');
      });
    },
    refetchRelmons() {
      this.$emit('refetchRelmons')
    },
    niceDate: function (time) {
      return dateFormat(new Date(time * 1000), 'yyyy-mm-dd HH:MM')
    },
    niceSize: function(size) {
      if (size < 1024) {
        return size + ' B'
      }
      if (size < 1048576) {
        return (size / 1024.0).toFixed(2) + ' KB'
      }
      if (size < 1073741824) {
        return (size / 1048576.0).toFixed(2) + ' MB'
      }

      return (size / 1073741824.0).toFixed(2) + ' GB'
    },
    getPairs: function(category) {
      let categoryName = category.name;
      if (categoryName in this.pairingCache) {
        return this.pairingCache[categoryName];
      }

      let pairs = [];
      let references = category.reference.reduce((arr, reference) => ({...arr, [reference.name]: reference}), {});
      let targets = category.target.reduce((arr, target) => ({...arr, [target.name]: target}), {});

      for (let reference of category.reference) {
        if (reference.match && reference.match.length && reference.match in targets) {
          pairs.push({'reference': reference, 'target': targets[reference.match]});
          delete references[reference.name];
          delete targets[reference.match];
        }
      }
      for (let reference of category.reference) {
        if (reference.name in references) {
          pairs.push({'reference': reference, 'target': undefined});
        }
      }
      for (let target of category.target) {
        if (target.name in targets) {
          pairs.push({'reference': undefined, 'target': target});
        }
      }

      this.pairingCache[categoryName] = pairs;
      return pairs;
    }
  }
}
</script>

<style scoped>
li {
  padding-bottom: 4px;
}

.red-text {
  color: red;
}

.green-text {
  color: #229955;
}

.gray-text {
  color: #7f8c8d;
}

.blinking-text {
  color: #2980b9;
  animation: blinker 1.5s ease-in-out infinite;
}

@keyframes blinker {
  50% {
    opacity: 0.2;
  }
}

.progress-bar {
  max-width: 250px;
  color: white !important;
  border-radius: 4px
}

.small-font {
  font-size: 12px;
  letter-spacing: -0.3px;
}

table, tr, td, th {
  border: 1px solid black;
  border-collapse: collapse;
  padding: 4px;
}

td {
  letter-spacing: -0.2px;
  font-size: 13px;
}

th {
  font-size: 15px;
  font-weight: 400;
  background: #eee;
}

tr:hover {
  background: #eee;
}

table {
  width: 100%;
}

.table-wrapper {
  width: 100%;
  margin-bottom: 24px;
  overflow-x: auto;
}

.file-info {
  text-align: center;
  white-space: nowrap;
}

</style>
